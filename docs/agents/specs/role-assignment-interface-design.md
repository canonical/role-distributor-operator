| Index | TBD | Type | Standards Specification |
| :---- | :---- | :---- | :---- |
| Title | Role Assignment Relation Interface | Status | Drafting |
| Author | Guillaume Boutry | Created | 2026-03-18 |
| Scope | Juju relation contract for distributing roles to units across diverse applications | Reviewers | TBD |

# Abstract

This specification defines the `role-assignment` Juju relation interface — a contract between a central Role Distributor charm (Provider) and diverse application charms (Requirers) that need role assignments distributed to their units. The Provider receives a cluster topology as input (out of scope for this spec), correlates it with registered Requirer units, and publishes per-unit role assignments through its App databag. The interface is cross-model capable and makes no assumptions about the Requirer workloads, allowing any application to participate by implementing a minimal registration contract.

# Rationale

Distributed systems like Sunbeam deploy multiple cooperating applications (MicroCeph, MicroOVN, etc.) across a shared pool of machines. Each application's units need to know what role they should assume — control-plane, storage, networking, gateway — based on the operator's desired cluster topology. Today, there is no standard Juju mechanism for a central authority to communicate role assignments to units across different applications and models. Each application either hard-codes its own role logic or requires manual per-unit configuration, which doesn't scale and creates a fragmented operator experience.

This specification defines a minimal, decoupled relation interface that allows a single Provider charm to act as the authoritative source of role assignments for any number of Requirer applications, across model boundaries.

## Goals

This specification has the following goals:

1. Define a cross-model-capable Juju relation interface (`role-assignment`) for distributing per-unit role assignments from a central Provider to diverse Requirers.
2. Keep the Requirer contract minimal — units need only register their identity.
3. Allow the Provider to assign multiple roles per unit.
4. Provide a recommended vendor-neutral role taxonomy while keeping role values as free-form strings.
5. Specify exact JSON schemas for all databags to enable independent, interoperable implementations.
6. Support optional machine-level configuration that the Provider can resolve to individual units, with clear precedence rules when both machine-level and unit-level configuration exist.
7. Allow the Provider to pass arbitrary workload parameters (`workload-params`) alongside role assignments.

## Non-goals

The following items are out of scope for this specification:

- Defining how the Provider acquires its topology input (operator config, action, upstream relation — all are valid).  
- Specifying Requirer-side workload behavior in response to role assignments.  
- Enforcing a closed set of role values at the schema level.  
- Defining the Provider charm's internal scheduling logic.

# Specification

## Interface overview and data flow

**Interface name:** `role-assignment`

**Relation type:** Regular (not peer, not subordinate)

**Cross-model:** Required. All communication happens exclusively through relation databags — no Juju API introspection of remote models.

**Topology:**

```
graph LR
    RD["Role Distributor<br/>(Provider)<br/>provides: role-assignment"]

    MC["MicroCeph (app)<br/>units: 0, 1, 2"]
    MO["MicroOVN (app)<br/>units: 0, 1"]
    AN["App N ..."]

    RD <-- "role-assignment" --> MC
    RD <-- "role-assignment" --> MO
    RD <-- "role-assignment" --> AN
```

Each Requirer app establishes one `role-assignment` relation with the Provider. The Provider sees each relation independently but writes a unified assignment mapping on each.

**Data flow:**

1. **Registration** — On `relation-joined` / `relation-changed`, each Requirer unit writes its `unit-name` and optionally its `machine-id` to its own Unit databag. The Requirer leader writes `model-name` and `application-name` to the App databag.
2. **Assignment** — The Provider leader reads all Requirer Unit and App databags across all relations. It correlates registered units against its topology input (using unit names directly, or machine IDs when available) and writes a per-unit assignment mapping to the **Provider App databag on each relation**. When the Provider has both machine-level and unit-level configuration for a unit, it resolves them according to the precedence rules defined in the Resolution semantics section.
3. **Consumption** — Each Requirer unit reads the Provider App databag on its relation, finds its own entry by `unit-name`, and acts on the assigned roles and `workload-params`.

**Important:** The Provider writes to its own App databag *per relation*. Each relation's Provider App databag contains only the assignments for the units on that relation (i.e., units of that specific Requirer app), not the entire cluster mapping.

## Databag schemas

### **Requirer App databag**

Written by the Requirer leader unit. Contains app-level identity.

```json
{
  "model-name": "microceph-model",
  "application-name": "microceph"
}
```

**JSON Schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RoleAssignmentRequirerAppDatabag",
  "type": "object",
  "properties": {
    "model-name": {
      "type": "string",
      "description": "The Juju model name where the Requirer application is deployed."
    },
    "application-name": {
      "type": "string",
      "description": "The real Juju application name of the Requirer. Required because cross-model relation aliases may differ from the actual application name."
    }
  },
  "required": ["model-name", "application-name"]
}
```

**Note:** These schemas describe only the application-managed portion of the databag. Juju injects additional keys into relation databags (e.g., `ingress-address`, `egress-subnets`, `private-address` in unit databags). Validators must filter out Juju-managed keys before applying these schemas.

### **Requirer Unit databag**

Written by each Requirer unit. Contains unit identity and optionally the machine ID.

```json
{
  "unit-name": "microceph/0",
  "machine-id": "0"
}
```

**JSON Schema:**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RoleAssignmentRequirerUnitDatabag",
  "type": "object",
  "properties": {
    "unit-name": {
      "type": "string",
      "description": "The Juju unit name (e.g. 'microceph/0'), derived from self.unit.name in the ops framework.",
      "pattern": "^[a-z][a-z0-9]*(-[a-z0-9]+)*/[0-9]+$"
    },
    "machine-id": {
      "type": "string",
      "description": "The Juju machine ID where this unit is running. Only meaningful in machine-model deployments; absent in Kubernetes models."
    }
  },
  "required": ["unit-name"]
}
```

### **Provider App databag**

Written by the Provider leader. Contains a JSON-dumped mapping of unit assignments for the units on this specific relation.

```json
{
  "assignments": "{\"microceph/0\": {\"roles\": [\"control\", \"storage\", \"gateway\"], \"workload-params\": {\"flavors\": [\"rgw\"]}, \"status\": \"assigned\"}, \"microceph/1\": {\"roles\": [\"storage\"], \"status\": \"assigned\"}, \"microceph/2\": {\"status\": \"error\", \"message\": \"unit not found in topology\"}}"
}
```

The `assignments` value is a JSON-encoded string (since Juju databag values are always strings). When parsed, its schema is:

**JSON Schema (outer):**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RoleAssignmentProviderAppDatabag",
  "type": "object",
  "properties": {
    "assignments": {
      "type": "string",
      "description": "JSON-encoded mapping of unit names to their role assignments."
    }
  }
}
```

**Note:** As with all databag schemas in this spec, this describes only the application-managed portion. Validators must filter out Juju-managed keys before applying the schema.

The `assignments` key is absent before the Provider has processed any units. Requirers must treat a missing `assignments` key as "not yet processed" (see Requirer-side validation).

**JSON Schema (parsed `assignments` value):**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RoleAssignmentMap",
  "type": "object",
  "additionalProperties": {
    "type": "object",
    "properties": {
      "roles": {
        "type": "array",
        "items": { "type": "string" },
        "description": "List of assigned roles. Present when status is 'assigned'."
      },
      "status": {
        "type": "string",
        "description": "Current assignment state for this unit. Well-known values: 'assigned', 'pending', 'error'. Unknown values must be treated as 'pending' by Requirers for forward compatibility."
      },
      "message": {
        "type": "string",
        "description": "Human-readable explanation. Required when status is 'error', optional otherwise."
      },
      "workload-params": {
        "type": "object",
        "additionalProperties": true,
        "description": "Arbitrary key-value parameters for the unit's workload configuration. Optional. The Provider resolves these from machine-level and/or unit-level configuration (see Resolution semantics)."
      }
    },
    "required": ["status"],
    "allOf": [
      {
        "if": { "required": ["status"], "properties": { "status": { "const": "assigned" } } },
        "then": { "required": ["status", "roles"] }
      },
      {
        "if": { "required": ["status"], "properties": { "status": { "const": "error" } } },
        "then": { "required": ["status", "message"] }
      }
    ],
    "additionalProperties": true
  }
}
```

**Example — fully resolved relation:**

```json
{
  "microceph/0": { "status": "assigned", "roles": ["control", "storage", "gateway"], "workload-params": {"flavors": ["rgw"]} },
  "microceph/1": { "status": "assigned", "roles": ["storage"] },
  "microceph/2": { "status": "error", "message": "unit not found in topology" }
}
```

## Recommended role taxonomy

The `role-assignment` interface treats role values as opaque strings — any string is valid. However, to promote cross-application consistency and operator readability, this specification recommends the following vendor-neutral taxonomy drawn from distributed systems conventions:

| Role | Meaning | Example usage |
| :---- | :---- | :---- |
| `control` | Control-plane services: schedulers, monitors, managers, state machines | MicroCeph mons/mgr, mds, MicroOVN central (northbound/southbound DBs) |
| `storage` | Data persistence and I/O-path workloads | MicroCeph OSDs |
| `network` | Data-plane networking: packet forwarding, tunneling, traffic handling | MicroOVN chassis |
| `gateway` | External-facing endpoints: API gateways, object stores, metadata services | MicroCeph RGW, MicroCeph Ganesha, MicroOvn enable-chassis-as-gateway option |

**Guidelines for Requirer application authors:**

1. **Prefer standard names.** If a workload fits one of the roles above, use that name rather than inventing a new one.  
2. **Combine freely.** A unit may receive multiple roles (e.g., `["control", "storage"]`). The taxonomy assumes roles are composable.  
3. **Extend when needed.** Applications with workloads that don't fit the standard taxonomy may define their own role strings. The spec does not restrict this. Document application-specific roles in the Requirer charm's own documentation.  
4. **Keep roles coarse-grained.** Roles describe *what category of work* a unit performs, not implementation-level process names. Use `control` rather than `mon` or `manager`.

**Note:** The Provider charm is not required to validate role values against this taxonomy. It assigns whatever roles the topology input specifies. The taxonomy is a convention for operators and charm authors, not a schema constraint.

## Resolution semantics

The Provider's topology input may define configuration at two levels: **machine-level** (keyed by machine ID) and **unit-level** (keyed by unit name). When a Requirer unit registers with a `machine-id`, the Provider can resolve configuration from either or both levels.

**Precedence rules:**

1. **Roles:** Unit-level fully replaces machine-level. If the Provider has unit-level roles for a unit, those are used. If only machine-level roles exist for the machine where the unit runs, those are used. No merging.
2. **`workload-params`:** Shallow merge. Machine-level params form the base, unit-level params override individual keys. Keys present only at machine level are preserved.
3. If no applicable configuration exists for a unit, it receives `{"status": "pending"}`. This includes the case where machine-level configuration exists for the unit's machine but the unit did not register a `machine-id` — machine-level configuration is not applied without an explicit `machine-id`.

**Machine-level `workload-params` and application scoping:**

Machine-level `workload-params` are keyed by application name, since multiple applications may share a machine. The following illustrates a possible topology input structure (the topology input format itself is out of scope for this spec — this is shown only to explain how `workload-params` application scoping works):

```yaml
machine-0:
  workload-params:
    microceph:
      flavors: ["rgw"]
    microovn:
      some-key: some-value
```

The Provider uses the `application-name` from the Requirer App databag to select the correct slice. Unit-level `workload-params` are already application-specific and need no such scoping.

**Units without `machine-id`:** If a unit does not provide `machine-id`, only unit-level configuration applies. Machine-level configuration is silently ignored for that unit.

**Machine-model only:** `machine-id` is only meaningful in machine-model deployments. In Kubernetes models, this field is absent. Providers must not require its presence.

## Events and lifecycle

### **Requirer-side lifecycle**

| Juju event | Requirer action |
| :---- | :---- |
| `relation-joined` | Leader writes `model-name` and `application-name` to App databag. Each unit writes `unit-name` (and optionally `machine-id`) to its Unit databag. |
| `relation-changed` | Each unit reads the Provider App databag, looks up its own `unit-name` in the parsed `assignments` map, and reacts to the `status`/`roles`/`workload-params` values. |
| `relation-departed` | Do not do anything. |
| `relation-broken` | App-level cleanup. All role assignments are considered revoked. It is up to the requirer to decide which action to take. |

### **Provider-side lifecycle**

| Juju event | Provider action |
| :---- | :---- |
| `relation-joined` | Note the new relation. Read the joining unit's Unit databag if available (cross-model databags may not be populated immediately; rely on `relation-changed` for complete data). |
| `relation-changed` | Re-read all Requirer Unit and App databags across all relations. Correlate registered units against the current topology. Write updated `assignments` to the Provider App databag on each affected relation. |
| `relation-departed` | Remove the departing unit from the `assignments` map. Re-evaluate topology if needed. |
| `relation-broken` | Clean up internal state for the departed Requirer app. |

**Reconciliation trigger:** The Provider should re-evaluate and re-publish assignments whenever:

- A Requirer unit joins or departs (relation events)  
- The topology input changes (out of scope for this spec, but the Provider must re-publish on all relations when it happens)

**Atomicity:** Juju hooks are serialized per unit. When the Provider updates assignments in response to a single event, it should update all affected relations within that hook invocation. This is effectively atomic from the Provider's perspective — Requirers on different relations will observe updates at different times (as their own `relation-changed` hooks fire), but the Provider's view is consistent at the point of writing.

### **Idempotency**

Both sides must treat `relation-changed` as idempotent. The Provider may re-write the same assignments, and Requirers must not reconfigure their workload if the assignment has not actually changed.

The interface library itself is **stateless** — it does not use `ops.StoredState` or any other local persistence. This is a deliberate design choice: `StoredState` is backed by a local SQLite file that is lost on Kubernetes pod recreation (e.g., charm refresh), making it unreliable for long-lived state. Instead, the library emits semantic events on every `relation-changed` that carries relevant data, and **charms are responsible for their own idempotency** (e.g., comparing the incoming assignment against the workload's current state before reconfiguring).

## Interface library and semantic events

Following standard Juju practice, the `role-assignment` interface should be implemented as a charm library (`charmcraft create-lib`) that wraps the raw relation databag operations behind semantic events and typed data classes.

### **Library location**

```
lib/charms/role_distributor/v0/role_assignment.py
```

### **Custom events**

**Provider-side events:**

| Event class | Emitted when | Handler receives |
| :---- | :---- | :---- |
| `RoleAssignmentUnitRegisteredEvent` | A new Requirer unit writes its `unit-name` to its Unit databag | `event.unit_name`, `event.model_name`, `event.application_name`, `event.machine_id`, `event.relation` |
| `RoleAssignmentUnitDepartedEvent` | A Requirer unit departs the relation | `event.unit_name`, `event.model_name`, `event.application_name`, `event.machine_id`, `event.relation` |

**Note on departure events:** During `relation-departed`, the departing unit's databag may already be cleared, especially in cross-model relations. Because the library is stateless, the `RoleAssignmentUnitDepartedEvent` can only be emitted when the departing unit's `unit-name` is still readable from the databag. If the databag is already cleared, the event is silently skipped. Charms that need guaranteed departure notification should observe `relation-broken` as a fallback.

**Requirer-side events:**

| Event class | Emitted when | Handler receives |
| :---- | :---- | :---- |
| `RoleAssignmentChangedEvent` | The Provider updates the `assignments` databag and this unit has an entry (any status, including `pending` and `error`) | `event.roles`, `event.status`, `event.message`, `event.workload_params`, `event.relation` |
| `RoleAssignmentRevokedEvent` | The relation is broken or this unit's entry is removed | `event.relation` |

### **Data classes**

```py
@dataclasses.dataclass(frozen=True)
class UnitRoleAssignment:
    """A single unit's role assignment as read from the Provider App databag."""
    status: Literal["assigned", "pending", "error"]
    roles: tuple[str, ...] = ()
    message: str | None = None
    workload_params: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True)
class RegisteredUnit:
    """A Requirer unit's registration as read from the relation databags."""
    unit_name: str
    model_name: str
    application_name: str
    machine_id: str | None = None
```

### **Provider-side interface object**

```py
class RoleAssignmentProvider(ops.Object):
    on: RoleAssignmentProviderEvents

    def set_assignments(
        self, relation: ops.Relation, assignments: dict[str, UnitRoleAssignment]
    ) -> None:
        """Write the full assignment map to the Provider App databag for a relation."""
        ...

    def get_registered_units(
        self, relation: ops.Relation
    ) -> list[RegisteredUnit]:
        """Read all Requirer unit registrations from a single relation."""
        ...

    def get_all_registered_units(self) -> list[RegisteredUnit]:
        """Read all Requirer unit registrations across all relations."""
        ...
```

### **Requirer-side interface object**

```py
class RoleAssignmentRequirer(ops.Object):
    on: RoleAssignmentRequirerEvents

    def get_assignment(self) -> UnitRoleAssignment | None:
        """Read this unit's assignment from the Provider App databag.
        Returns None if no entry exists for this unit."""
        ...
```

The library handles:

- Writing `model-name`, `application-name`, `unit-name`, and `machine-id` (when available) to the appropriate databags automatically on `relation-joined`
- Parsing the `assignments` JSON string from the Provider App databag  
- Emitting `RoleAssignmentChangedEvent` on every `relation-changed` where this unit has an entry in the `assignments` map (regardless of status)
- Emitting `RoleAssignmentRevokedEvent` on `relation-broken`

The library is stateless — it does not use `ops.StoredState`. Charms are responsible for their own idempotency.

### **Usage example — Requirer charm**

```py
class MicroCephCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.role_assignment = RoleAssignmentRequirer(self, "role-assignment")
        self.framework.observe(
            self.role_assignment.on.role_assignment_changed,
            self._on_role_changed,
        )
        self.framework.observe(
            self.role_assignment.on.role_assignment_revoked,
            self._on_role_revoked,
        )

    def _on_role_changed(self, event: RoleAssignmentChangedEvent):
        if event.status == "assigned":
            self._configure_workload(event.roles, event.workload_params)
        elif event.status == "error":
            self.unit.status = ops.BlockedStatus(event.message)

    def _on_role_revoked(self, event: RoleAssignmentRevokedEvent):
        self._reset_to_default()
```

## `charmcraft.yaml` integration

### **Provider charm (`role-distributor`)**

```
provides:
  role-assignment:
    interface: role-assignment
```

### **Requirer charm (e.g., `microceph`, `microovn`)**

```
requires:
  role-assignment:
    interface: role-assignment
    limit: 1
```

The `limit: 1` ensures a Requirer app connects to exactly one Provider. Multiple Providers assigning roles to the same app would create conflicts.

## Validation and failure semantics

### **Provider-side validation**

The Provider should enforce the following before publishing assignments:

| Condition | Behavior |
| :---- | :---- |
| Unit registered but not present in topology | Write `{"status": "error", "message": "unit not found in topology"}` for that unit |
| Unit registered but topology not yet loaded | Write `{"status": "pending"}` for that unit |
| Role value in topology is not recognized by the Provider | Pass it through. The Provider does not validate role strings — it is a router, not an enforcer |
| Duplicate unit-name across relations | Should not happen (unit names are globally unique in Juju). If detected, write `error` status for the duplicates |

### **Requirer-side validation**

| Condition | Behavior |
| :---- | :---- |
| Provider App databag has no `assignments` key | Treat as no assignment yet. Do not error. |
| `assignments` JSON is malformed | Log warning, set `BlockedStatus`, do not configure workload |
| Unit's entry has `status: "assigned"` but `roles` list is empty | Treat as a valid but no-op assignment. Log warning. |
| Unit's entry has unknown `status` value | Log warning, treat as `pending` (forward-compatible) |
| Unit's entry has a role string the Requirer does not recognize | Log warning, ignore the unrecognized role, apply known roles |
| `workload-params` contains keys the Requirer does not recognize | Log warning, ignore unrecognized keys, use known keys |

### **Relation stability**

The interface must tolerate temporary inconsistency during scaling events. When multiple units join simultaneously, the Provider may not see all registrations in a single `relation-changed` hook invocation. Requirers must not assume that the absence of their entry is permanent — they should wait for subsequent `relation-changed` events.

## Risks and mitigations

| Risk | Mitigation |
| :---- | :---- |
| Provider topology input lags behind unit registrations | Provider writes `pending` for unresolved units; Requirers wait gracefully |
| Cross-model relation latency delays assignments | Requirer workloads must not hard-fail on missing assignments; treat as `pending` until resolved |
| Provider leader change mid-reconciliation | Juju guarantees only the leader writes to the App databag. New leader should re-read all unit databags and re-publish assignments on `leader-elected` |
| Requirer unit departs but Provider retains stale entry | Provider must clean up assignments on `relation-departed`; the interface library should handle this automatically |
| Multiple Provider charms deployed by mistake | `limit: 1` on the Requirer side prevents connecting to more than one Provider |
| Large number of units causes oversized App databag | Juju databag size limit is \~1 MiB. Each unit entry is \~100 bytes. This supports \~10,000 units per relation, which is well beyond practical limits |
| Role taxonomy drift across teams | The recommended taxonomy is documented in this spec. Charm authors should reference it. The spec does not enforce it at the schema level to preserve flexibility |
| Provider assigns roles the Requirer doesn't understand | Requirer logs a warning and ignores unrecognized roles. The Requirer's own documentation defines its supported roles |
| Requirer runs on ops < 3.5.1 and cannot provide `machine-id` | `machine-id` is optional; units without it receive only unit-level configuration. Machine-level config is silently skipped |
| Machine-level `workload-params` missing entry for a Requirer's application | No machine-level `workload-params` for that app; only unit-level applies (if any). Not an error |

## Documentation impact

The implementation should be accompanied by:

- **Interface library docstrings** — inline documentation in `role_assignment.py` covering the semantic events, data classes, and usage examples for both Provider and Requirer sides  
- **Charm library README** — published to Charmhub with the library, explaining the interface contract, databag schemas, and the recommended role taxonomy  
- **Provider charm documentation** — how operators feed topology input (out of scope for this spec, but the Provider charm must document its own input mechanism)  
- **Requirer charm documentation** — each Requirer charm must document which role strings it supports and what workload behavior each role triggers

# Spec History and Changelog {#spec-history-and-changelog}

| Date | Status | Author | Change |
|------|--------|--------|--------|
| 2026-03-18 | Drafting | Guillaume Boutry | Initial draft |
| 2026-03-24 | Drafting | Guillaume Boutry | Add optional `machine-id` in Requirer Unit databag, required `application-name` in Requirer App databag, optional `workload-params` in assignment entries, and new Resolution semantics section (machine-level vs unit-level precedence) |

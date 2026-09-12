"""Portable, strict domain contracts. No browser-provider dependencies."""
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Action(StrEnum):
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    WAIT = "wait"


class Risk(StrEnum):
    READ = "READ"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    SENSITIVE = "SENSITIVE"
    IRREVERSIBLE = "IRREVERSIBLE"


class Status(StrEnum):
    SUCCESS = "SUCCESS"
    BUSINESS_OUTCOME = "BUSINESS_OUTCOME"
    RECOVERABLE_ERROR = "RECOVERABLE_ERROR"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    HARD_FAILURE = "HARD_FAILURE"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_HUMAN = "REQUIRE_HUMAN"


AccessibilityRole = Literal[
    "alert", "alertdialog", "application", "article", "banner", "blockquote",
    "button", "caption", "cell", "checkbox", "code", "columnheader", "combobox",
    "complementary", "contentinfo", "definition", "deletion", "dialog", "directory",
    "document", "emphasis", "feed", "figure", "form", "generic", "grid", "gridcell",
    "group", "heading", "img", "insertion", "link", "list", "listbox", "listitem",
    "log", "main", "marquee", "math", "menu", "menubar", "menuitem",
    "menuitemcheckbox", "menuitemradio", "meter", "navigation", "none", "note",
    "option", "paragraph", "presentation", "progressbar", "radio", "radiogroup",
    "region", "row", "rowgroup", "rowheader", "scrollbar", "search", "searchbox",
    "separator", "slider", "spinbutton", "status", "strong", "subscript",
    "superscript", "switch", "tab", "table", "tablist", "tabpanel", "term",
    "textbox", "time", "timer", "toolbar", "tooltip", "tree", "treegrid", "treeitem",
]


class Accessibility(Model):
    type: Literal["accessibility"] = "accessibility"
    role: AccessibilityRole
    name: str = Field(min_length=1)


class Label(Model):
    type: Literal["label"] = "label"
    value: str = Field(min_length=1)


class Text(Model):
    type: Literal["text"] = "text"
    value: str = Field(min_length=1)


class CSS(Model):
    type: Literal["css"] = "css"
    value: str = Field(min_length=1)


Anchor = Annotated[Accessibility | Label | Text | CSS, Field(discriminator="type")]


class Relative(Model):
    """Find an exact named role within a unique semantic container."""
    type: Literal["relative"] = "relative"
    anchor: Anchor
    role: AccessibilityRole
    name: str = Field(min_length=1)


Strategy = Annotated[Accessibility | Label | Text | Relative | CSS, Field(discriminator="type")]


class SemanticTarget(Model):
    concept: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    strategies: list[Strategy] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def css_last(self):
        seen_css = False
        for strategy in self.strategies:
            if seen_css and strategy.type != "css":
                raise ValueError("CSS strategies must be last-resort fallbacks")
            seen_css |= strategy.type == "css"
        return self


class Expectation(Model):
    kind: Literal["visible", "absent", "text_equals"] = "visible"
    value: str | None = None

    @model_validator(mode="after")
    def valid_value(self):
        if (self.kind == "text_equals") != (self.value is not None):
            raise ValueError("Only text_equals requires a value")
        return self


class Condition(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    target: SemanticTarget
    expected: Expectation = Field(default_factory=Expectation)


class RetryPolicy(Model):
    max_attempts: int = Field(default=1, ge=1, le=3)
    delay_ms: int = Field(default=100, ge=0, le=2000)
    safe_to_repeat: bool = False

    @model_validator(mode="after")
    def repeat_requires_declaration(self):
        if self.max_attempts > 1 and not self.safe_to_repeat:
            raise ValueError("Retries require explicit safe_to_repeat")
        return self


class FieldSpec(Model):
    type: Literal["string", "decimal", "integer", "boolean"]
    description: str = ""
    sensitive: bool = True


class Step(Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    action: Action
    target: SemanticTarget
    input: str | None = None
    output: str | None = None
    precondition: Condition | None = None
    postcondition: Condition | None = None
    timeout_ms: int = Field(default=3000, ge=1, le=60000)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    risk: Risk

    @model_validator(mode="after")
    def action_fields(self):
        if (self.action == Action.FILL) != (self.input is not None):
            raise ValueError("Only fill requires input")
        if (self.action == Action.EXTRACT) != (self.output is not None):
            raise ValueError("Only extract requires output")
        if self.action == Action.WAIT and self.postcondition is None:
            raise ValueError("wait requires a postcondition")
        if self.action == Action.FILL and self.risk == Risk.READ:
            raise ValueError("fill cannot be READ")
        return self


class BusinessOutcome(Model):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    description: str
    condition: Condition


class Compatibility(Model):
    application: str = Field(min_length=1)
    application_version: str = Field(min_length=1)
    surface_contract: Literal["1"] = "1"
    required_features: list[Literal["accessibility", "label", "text", "relative", "css"]]


class SafetyMetadata(Model):
    approved_for_replay: bool = False
    max_risk: Risk = Risk.READ
    notes: str = ""


class CapabilityArtifact(Model):
    schema_version: Literal["1.0"]
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(min_length=1)
    description: str
    inputs: dict[str, FieldSpec]
    outputs: dict[str, FieldSpec]
    steps: list[Step] = Field(min_length=1)
    success: Condition
    business_outcomes: list[BusinessOutcome] = Field(default_factory=list)
    compatibility: Compatibility
    safety: SafetyMetadata

    @model_validator(mode="after")
    def coherent(self):
        import re
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate step IDs")
        codes = [outcome.code for outcome in self.business_outcomes]
        if len(codes) != len(set(codes)):
            raise ValueError("Duplicate business outcome codes")
        captured = [step.output for step in self.steps if step.output is not None]
        if len(captured) != len(set(captured)) or set(captured) != set(self.outputs):
            raise ValueError("Each declared output must be extracted exactly once")
        for key in [*self.inputs, *self.outputs]:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
                raise ValueError("Invalid field name")
        conditions = [self.success, *(outcome.condition for outcome in self.business_outcomes)]
        templates = [step.input for step in self.steps if step.input is not None]
        for step in self.steps:
            conditions.extend(condition for condition in (step.precondition, step.postcondition) if condition is not None)
        templates.extend(condition.expected.value for condition in conditions if condition.expected.value is not None)
        for template in templates:
            remainder = re.sub(r"{{\s*inputs\.([a-z][a-z0-9_]*)\s*}}", "", template)
            refs = re.findall(r"{{\s*inputs\.([a-z][a-z0-9_]*)\s*}}", template)
            if "{{" in remainder or "}}" in remainder or any(ref not in self.inputs for ref in refs):
                raise ValueError("Invalid or undeclared input template")
        return self


Scalar = str | Decimal | int | bool


class TargetRef(Model):
    """Opaque provider-owned handle, never a browser object."""
    token: str


class MatchSet(Model):
    targets: list[TargetRef] = Field(default_factory=list)
    ambiguous_scope: bool = False


class Observation(Model):
    url: str = ""
    title: str = ""
    elements: list["ObservedElement"] = Field(default_factory=list)
    dialogs: list[str] = Field(default_factory=list)
    frames: list["FrameInfo"] = Field(default_factory=list)
    visible: bool
    text: str = ""  # Transient only: must never be sent to evidence.


class ResolutionAttempt(Model):
    strategy: str
    index: int
    matches: int
    diagnostic: Literal["unique", "no_match", "ambiguous", "ambiguous_scope"]


class ResolutionResult(Model):
    succeeded: bool
    strategy: str | None = None
    quality: Literal["semantic", "structural", "css_fallback", "unresolved"] = "unresolved"
    target: TargetRef | None = None
    matches: int = 0
    code: Literal["RESOLVED", "NO_TARGET", "AMBIGUOUS_TARGET"]
    attempts: list[ResolutionAttempt]


class Failure(Model):
    run_id: str
    step_id: str | None = None
    code: str
    expected_condition: str | None = None
    observed_condition: str | None = None
    retryable: bool = False
    safe_next_action: str
    evidence_refs: list[str] = Field(default_factory=list)


class RunResult(Model):
    run_id: str
    model_calls: Literal[0] = 0
    status: Status
    outputs: dict[str, Scalar] = Field(default_factory=dict)
    business_code: str | None = None
    failure: Failure | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class ObservedElement(Model):
    id: str
    role: str
    name: str
    label: str = ""
    text: str = ""
    kind: str
    enabled: bool = True
    visible: bool = True
    value: str | None = None
    target: SemanticTarget


class FrameInfo(Model):
    title: str
    path: str


Observation.model_rebuild()

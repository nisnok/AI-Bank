"""Read visible application identity through Surface, never simulator internals."""
from deterministic_ui.models import Accessibility, SemanticTarget
from deterministic_ui.resolver import LocatorResolver
from deterministic_ui.surface import Surface
from .binder import BindingError
from .models import ObservedApplication


async def observe_application(surface: Surface) -> ObservedApplication:
    values = {}
    for key, label in (("tenant_id","Institution identifier"), ("product","Application product"),
                       ("application_version","Application version")):
        target = SemanticTarget(concept=key, strategies=[Accessibility(role="status", name=label)])
        resolved = await LocatorResolver().resolve(target, surface)
        if not resolved.succeeded or resolved.target is None:
            raise BindingError("APPLICATION_IDENTITY_NOT_VERIFIED")
        observation = await surface.observe(resolved.target)
        if not observation.visible or not observation.text.strip():
            raise BindingError("APPLICATION_IDENTITY_NOT_VERIFIED")
        values[key] = observation.text.strip()
    await surface.release_targets()
    try:
        return ObservedApplication(**values)
    except ValueError:
        raise BindingError("APPLICATION_IDENTITY_NOT_VERIFIED") from None

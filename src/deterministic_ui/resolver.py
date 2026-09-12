from .models import ResolutionAttempt, ResolutionResult, SemanticTarget
from .surface import Surface


class LocatorResolver:
    async def resolve(self, target: SemanticTarget, surface: Surface) -> ResolutionResult:
        attempts = []
        for index, strategy in enumerate(target.strategies):
            matches = await surface.query(strategy)
            count = len(matches.targets)
            diagnostic = "ambiguous_scope" if matches.ambiguous_scope else (
                "ambiguous" if count > 1 else "unique" if count == 1 else "no_match"
            )
            attempts.append(ResolutionAttempt(strategy=strategy.type, index=index,
                                               matches=count, diagnostic=diagnostic))
            if matches.ambiguous_scope or count > 1:
                return ResolutionResult(succeeded=False, strategy=strategy.type, matches=count,
                                        code="AMBIGUOUS_TARGET", attempts=attempts)
            if count == 1:
                quality = "structural" if strategy.type == "relative" else (
                    "css_fallback" if strategy.type == "css" else "semantic"
                )
                return ResolutionResult(succeeded=True, strategy=strategy.type, quality=quality,
                                        target=matches.targets[0], matches=1, code="RESOLVED", attempts=attempts)
        return ResolutionResult(succeeded=False, code="NO_TARGET", attempts=attempts)

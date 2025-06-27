from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Competition

def competition_permission_required(permission_type):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # Handle both 'competition_pk' and 'pk'
            competition_pk = kwargs.get('competition_pk') or kwargs.get('pk')
            if not competition_pk:
                raise KeyError("Expected 'pk' or 'competition_pk' in URL kwargs.")

            competition = get_object_or_404(Competition, pk=competition_pk)

            if permission_type == 'full' and not competition.has_full_access(request.user):
                raise PermissionDenied
            elif permission_type == 'any' and not competition.has_any_access(request.user):
                raise PermissionDenied

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


class CompetitionAccessMixin:
    access_level = 'any'  # or 'full'

    def dispatch(self, request, *args, **kwargs):
        # Handle either 'competition_pk' or 'pk'
        competition_pk = kwargs.get('competition_pk') or kwargs.get('pk')
        competition = get_object_or_404(Competition, pk=competition_pk)

        if self.access_level == 'full' and not competition.has_full_access(request.user):
            raise PermissionDenied
        if self.access_level == 'any' and not competition.has_any_access(request.user):
            raise PermissionDenied

        # Optional: preload self.competition
        self.competition = competition

        return super().dispatch(request, *args, **kwargs)

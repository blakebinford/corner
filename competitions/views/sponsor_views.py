
from django.forms import modelformset_factory
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from django.views.generic import FormView, TemplateView


from competitions.models import Competition, Sponsor
from competitions.forms import SponsorLogoForm, SponsorEditForm

class SponsorEditView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'competitions/sponsor_edit.html'

    def test_func(self):
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        return self.request.user == competition.organizer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        context['competition'] = competition

        SponsorFormSet = modelformset_factory(
            Sponsor,
            form=SponsorEditForm,
            extra=0,
            can_delete=True,
        )

        context['formset'] = SponsorFormSet(queryset=competition.sponsor_logos.all())
        context['upload_url'] = reverse_lazy('competitions:sponsor_logo_upload',
                                             kwargs={'competition_pk': competition_pk})
        return context

    def post(self, request, *args, **kwargs):
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        SponsorFormSet = modelformset_factory(
            Sponsor,
            form=SponsorEditForm,
            extra=0,
            can_delete=True,
        )

        formset = SponsorFormSet(request.POST, request.FILES, queryset=competition.sponsor_logos.all())

        if formset.is_valid():
            # Save formset changes
            sponsors = formset.save(commit=False)
            for sponsor in sponsors:
                display_order_field = f"display_order_{sponsor.pk}"
                if display_order_field in request.POST:
                    sponsor.display_order = int(request.POST[display_order_field])
                sponsor.save()

                # Handle deletions
            for deleted_sponsor in formset.deleted_objects:
                deleted_sponsor.delete()

            return redirect('competitions:competition_detail', pk=competition_pk)
        else:
            print("Formset errors:", formset.errors)
            return self.render_to_response(self.get_context_data(formset=formset))

class SponsorLogoUploadView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    form_class = SponsorLogoForm
    template_name = 'competitions/sponsor_logo_form.html'  # Create this template
    success_url = reverse_lazy('competitions:competition_list')

    def test_func(self):
        """
        Checks if the logged-in user is the organizer of the competition.
        """
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)
        return self.request.user == competition.organizer

    def form_valid(self, form):
        """
        Handles the form submission for uploading sponsor logos.
        """
        competition_pk = self.kwargs['competition_pk']
        competition = get_object_or_404(Competition, pk=competition_pk)

        if self.request.FILES.getlist('sponsor_logos'):
            for logo in self.request.FILES.getlist('sponsor_logos'):
                sponsor = Sponsor.objects.create(
                    name=logo.name,  # Or a more descriptive name
                    logo=logo
                )
                competition.sponsor_logos.add(sponsor)

        return super().form_valid(form)
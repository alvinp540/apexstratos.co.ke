from django import forms

from .tutorial_import import MAX_BUNDLE_BYTES


class DailyTutorialBundleForm(forms.Form):
    month = forms.IntegerField(min_value=1, label='Curriculum month')
    week = forms.IntegerField(min_value=1, max_value=4)
    day = forms.ChoiceField(choices=(('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'), ('3', 'Thursday')))
    scheduled_for = forms.DateTimeField(
        input_formats=('%Y-%m-%dT%H:%M',),
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text='The local schedule date and time for all twenty tutorials.',
    )
    bundle = forms.FileField(help_text='ZIP: manifest.json plus 20 internal MP4 videos. Maximum 1.5 GB.')

    def clean_bundle(self):
        bundle = self.cleaned_data['bundle']
        if not bundle.name.lower().endswith('.zip'):
            raise forms.ValidationError('Upload a .zip tutorial bundle.')
        if bundle.size > MAX_BUNDLE_BYTES:
            raise forms.ValidationError('The bundle may not exceed 1.5 GB.')
        return bundle

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):
    """Passenger registration: identity + passphrase."""

    first_name = forms.CharField(
        label='Full name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'placeholder': 'Amara Okonkwo',
            'autocomplete': 'name',
        }),
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'placeholder': 'you@earth.io',
            'autocomplete': 'email',
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('first_name', 'username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'placeholder': 'starfarer',
            'autocomplete': 'username',
        })
        self.fields['username'].help_text = 'Letters, digits and @/./+/-/_ only.'
        self.fields['password1'].help_text = ''
        self.fields['password1'].widget.attrs.update({
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
        self.fields['password2'].help_text = 'Repeat it to confirm.'
        self.fields['password2'].widget.attrs.update({
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A passenger already uses that email address.')
        return email


class LoginForm(AuthenticationForm):
    """Sign-in with passenger name and passphrase."""

    username = forms.CharField(
        label='Passenger name',
        widget=forms.TextInput(attrs={
            'placeholder': 'starfarer',
            'autocomplete': 'username',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label='Passphrase',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        }),
    )

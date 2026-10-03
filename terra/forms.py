import io
from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Profile


class SignupForm(UserCreationForm):
    """Passenger registration: identity + passphrase."""

    first_name = forms.CharField(
        label=_('Full name'),
        max_length=150,
        widget=forms.TextInput(attrs={
            'placeholder': 'Amara Okonkwo',
            'autocomplete': 'name',
        }),
    )
    email = forms.EmailField(
        label=_('Email'),
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
        self.fields['username'].help_text = _('Letters, digits and @/./+/-/_ only.')
        self.fields['password1'].help_text = ''
        self.fields['password1'].widget.attrs.update({
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
        self.fields['password2'].help_text = _('Repeat it to confirm.')
        self.fields['password2'].widget.attrs.update({
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _('A passenger already uses that email address.'),
            )
        return email


class LoginForm(AuthenticationForm):
    """Sign-in with passenger name and passphrase."""

    username = forms.CharField(
        label=_('Passenger name'),
        widget=forms.TextInput(attrs={
            'placeholder': 'starfarer',
            'autocomplete': 'username',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label=_('Passphrase'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        }),
    )


class BuyForm(forms.Form):
    """Spend Earth credits on TerraX."""

    amount = forms.DecimalField(
        label=_('Earth credits to spend'),
        min_value=Decimal('1.00'),
        max_value=Decimal('10000000.00'),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'placeholder': '250.00',
            'step': '0.01',
            'min': '1',
            'inputmode': 'decimal',
        }),
    )


class SellForm(forms.Form):
    """Sell TerraX back for Earth credits."""

    amount = forms.DecimalField(
        label=_('TerraX to sell'),
        min_value=Decimal('0.000001'),
        max_value=Decimal('100000000.000000'),
        max_digits=14,
        decimal_places=6,
        widget=forms.NumberInput(attrs={
            'placeholder': '0.250000',
            'step': '0.000001',
            'min': '0.000001',
            'inputmode': 'decimal',
        }),
    )


class AccountForm(forms.ModelForm):
    """Edit the passenger's identity record (user + profile fields)."""

    first_name = forms.CharField(
        label=_('Full name'),
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Amara Okonkwo'}),
    )
    email = forms.EmailField(
        label=_('Email'),
        required=False,
        widget=forms.EmailInput(attrs={'placeholder': 'you@earth.io'}),
    )
    date_of_birth = forms.DateField(
        label=_('Date of birth'),
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date', 'placeholder': 'YYYY-MM-DD',
        }),
    )

    class Meta:
        model = Profile
        fields = ('tagline', 'sector')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if kwargs.get('instance') is None and user is not None:
            self.instance = getattr(user, 'profile', None) or Profile(
                user=user,
            )
        if user is not None and not self.is_bound:
            dob = ''
            if hasattr(user, 'profile') and user.profile.date_of_birth:
                dob = user.profile.date_of_birth.isoformat()
            self.initial.update({
                'first_name': user.first_name,
                'email': user.email,
                'date_of_birth': dob,
            })

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exclude(
            pk=self.user.pk,
        ).exists():
            raise forms.ValidationError(
                _('A passenger already uses that email address.'),
            )
        return email

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > timezone.localdate():
            raise forms.ValidationError(_('That date is in the future.'))
        return dob

    def save(self, commit=True):
        user = self.user
        user.first_name = self.cleaned_data.get('first_name') or ''
        user.email = self.cleaned_data.get('email') or ''
        profile = super().save(commit=False)
        profile.user = user
        profile.date_of_birth = self.cleaned_data.get('date_of_birth') or None
        if commit:
            user.save()
            profile.save()
        return user


AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


class AvatarForm(forms.Form):
    """Validate + downscale a passenger photo (Pillow)."""

    avatar = forms.ImageField(
        label=_('Passenger photo'),
        help_text=_('JPEG or PNG, up to 2 MB. Resized to 640 px.'),
    )

    def clean_avatar(self):
        upload = self.cleaned_data['avatar']
        if upload.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError(_('Keep the photo under 2 MB.'))
        try:
            from PIL import Image, ImageOps

            img = Image.open(upload)
            img = ImageOps.exif_transpose(img)
            img.thumbnail((640, 640))
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            out = io.BytesIO()
            img.save(out, format='JPEG', quality=86, optimize=True)
            out.seek(0)
        except Exception as exc:  # noqa: BLE001 — surface as a form error
            raise forms.ValidationError(
                _('That file is not a readable image.'),
            ) from exc
        upload.name = f'{upload.name.rsplit(".", 1)[0]}.jpg'
        upload.file = out
        upload.size = out.getbuffer().nbytes
        return upload


class RatingForm(forms.Form):
    """Rate a Novarian agent from the account centre."""

    agent = forms.IntegerField(widget=forms.HiddenInput)
    rating = forms.IntegerField(
        label=_('Stars'),
        min_value=1,
        max_value=5,
        widget=forms.RadioSelect(
            attrs={'class': 'rt-stars'},
        ),
    )
    comment = forms.CharField(
        label=_('Comment'),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': _('How did the agent handle your signal?'),
        }),
    )

    def clean_agent(self):
        agent_id = self.cleaned_data['agent']
        if not User.objects.filter(pk=agent_id, is_active=True).exists():
            raise forms.ValidationError(_('Unknown agent.'))
        return agent_id


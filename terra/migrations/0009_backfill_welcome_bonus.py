"""Backfill the 10,000 TRX welcome bonus for wallets that never received it.

Accounts created before the welcome bonus existed — or outside the signup
flow (admin deck, ``createsuperuser``) — were left holding 0 TRX. Grant the
bonus once to every wallet whose ledger has never seen a single entry, so a
genuine 0 balance after spending is left untouched.
"""
from decimal import Decimal

from django.db import migrations

BONUS = Decimal('10000.000000')
NOTE = 'Welcome bonus · Expedition 01'


def grant_welcome_bonus(apps, schema_editor):
    Profile = apps.get_model('terra', 'Profile')
    Transaction = apps.get_model('terra', 'Transaction')
    seen_ledger = set(
        Transaction.objects.values_list('user_id', flat=True),
    )
    legacy = Profile.objects.filter(trx_balance=0).exclude(
        user_id__in=seen_ledger,
    )
    for profile in legacy:
        profile.trx_balance = BONUS
        profile.save(update_fields=['trx_balance'])
        Transaction.objects.create(
            user_id=profile.user_id,
            kind='bonus',
            trx=BONUS,
            usd=Decimal('0.00'),
            price_usd=Decimal('0.00'),
            note=NOTE,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('terra', '0008_profile_avatar_agentrating'),
    ]

    operations = [
        migrations.RunPython(grant_welcome_bonus, migrations.RunPython.noop),
    ]
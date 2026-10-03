"""Seed the ten Terra Nova newsroom dispatches.

Populates the News section at migrate time so the page is never empty;
``terra.news.ensure_news()`` keeps it topped up afterwards (idempotent,
keyed by slug).
"""
from django.db import migrations


def seed_news(apps, schema_editor):
    """Insert any missing dispatch from ``terra.news.NEWS_ITEMS``."""
    from datetime import timedelta

    from django.utils import timezone

    from terra.news import NEWS_ITEMS

    NewsItem = apps.get_model('terra', 'NewsItem')
    now = timezone.localtime()
    for slug, category, featured, hours_ago, title, summary, source, body in NEWS_ITEMS:
        NewsItem.objects.get_or_create(
            slug=slug,
            defaults={
                'title': title,
                'category': category,
                'summary': summary,
                'body': body,
                'source': source,
                'is_featured': featured,
                'published_at': now - timedelta(hours=hours_ago),
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('terra', '0010_newsitem'),
    ]

    operations = [
        migrations.RunPython(seed_news, migrations.RunPython.noop),
    ]

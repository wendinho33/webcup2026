"""The Terra Nova newsroom — seed content for the News section.

Ten dispatches covering the life of the colony, keyed by slug so the
seeder is idempotent: running it twice never duplicates an article.
"""
from datetime import timedelta

from django.utils import timezone

# (slug, category, is_featured, hours_ago, title, summary, source, body)
NEWS_ITEMS = [
    (
        'expedition-01-boarding-window-opens',
        'expedition',
        True,
        5,
        'Expedition 01 boarding window opens for the first thousand passengers',
        'Mission Control has released seat assignments for the transit window; '
        'passengers can review their dossier and QR boarding pass in Mission Control.',
        'Terra Nova Newsroom',
        'The transit window for Expedition 01 is officially open. Mission Control '
        'confirmed that the first one thousand confirmed passengers will be called '
        'in waves, ordered by the sector recorded on their passenger profile.\n\n'
        'Travellers should open Mission Control and check the dossier section before '
        'arrival: any mismatch between the fiscal code on file and the name on the '
        'passage claim will hold the reservation at the gate. The welcome bonus of '
        '10,000 TRX has already been credited to every claimed wallet, and fares for '
        'the first shuttle runs are expected to settle well below the expedition-era '
        'peak.\n\n'
        'Agents on Terra Chat will staff an extended desk through the whole boarding '
        'window. If your passage is missing, open a thread rather than re-registering '
        '— duplicate claims are the single biggest cause of delay at the gate.',
    ),
    (
        'heat-wave-eight-day-anomaly-forecast',
        'weather',
        False,
        11,
        'Heat wave holds: eight-day anomaly forecast issued for all four sectors',
        'The Aurelia observatory records a +7°C anomaly; every day of the simulation '
        'window crosses the alert threshold.',
        'Aurelia Observatory Wire',
        'The seasonal mean has been left far behind. The observatory\'s thermal model '
        'now shows an eight-day window in which every single day crosses the alert '
        'threshold, peaking well above the +7°C anomaly line.\n\n'
        'Heat alerts are being pushed to every paired device once per day for the '
        'duration of the window. Residents of the Glass Tundra — normally the cold '
        'reserve of the colony — are the hardest hit in relative terms, with the '
        'permafrost surface crossing freezing at midday.\n\n'
        'Civic advice is unchanged: move travel to the early morning, keep the '
        'Terra Watch band charged so heat-strain warnings reach the health record, '
        'and report any stalled cooling unit through a civic request rather than '
        'waiting for an inspection.',
    ),
    (
        'terrax-steadies-as-ledger-volume-doubles',
        'market',
        False,
        20,
        'TerraX steadies as ledger volume doubles week on week',
        'Exchange fee revenue funds the colony\'s service budget; traders watch the '
        '0.5% fee that settles every TerraX exchange.',
        'TerraX Desk',
        'After a volatile stretch, TerraX has found a tighter range against Earth '
        'credits as ledger volume doubled week on week. The exchange\'s 0.5% fee — '
        'split between every buy and sell — continues to flow into the colony '
        'service budget that underwrites transport and waste collection.\n\n'
        'Market watchers note that the peg mechanics remain untouched: one TerraX '
        'still tracks the reference basket that colonists have used since the first '
        'settlement, and the welcome-bonus wallets credited at sign-up keep new '
        'entrants buying from day one.\n\n'
        'The desk reminds traders that every settled trade prints a ledger entry '
        'visible in the account centre. Volume is welcome; surprises in the '
        'statement are not.',
    ),
    (
        'night-rails-return-to-glass-tundra',
        'transport',
        False,
        30,
        'Night rails return to the Glass Tundra after a six-week refit',
        'The northern line reopens with live departure boards and QR tickets '
        'accepted at every receiver aboard.',
        'Nova Transit',
        'The northern line through the Glass Tundra is back in service after a '
        'six-week refit of the sleeping cars and the signalling loop at the terminal '
        'approach.\n\n'
        'Departure boards on the transport page now list the restored night services '
        'alongside the daytime buses that thread the villages. Fares are payable in '
        'TerraX, and the QR ticket issued on purchase is scanned by the receiver '
        'aboard — paper tickets are no longer accepted on the northern run.\n\n'
        'Transit authorities expect the reopened line to take pressure off the '
        'Aurelia road corridor during the heat wave, when daytime road travel is '
        'discouraged. Night departures are already the fastest-selling services on '
        'the board.',
    ),
    (
        'council-opens-tax-window-for-the-season',
        'civic',
        False,
        44,
        'Council opens the season tax window; sector levies published',
        'Levies are set per sector and payable from the government portal before '
        'the window closes.',
        'Colony Council',
        'The season tax window is open. Sector levies — published in full on the '
        'government portal — are assessed on the passenger record and fall due '
        'before the window closes at the end of the season.\n\n'
        'Payment takes one press from the portal and writes a ledger entry against '
        'the TerraX wallet; Earth credit holders can settle at the same counter. '
        'The council notes that unpaid levies roll into the next season with an '
        'added collection charge, and that the pension disbursement scheduled each '
        'month is funded directly from the window.\n\n'
        'Passengers who believe their assessment is wrong can open a civic request '
        'and have it reviewed by a human agent rather than the automated assessor.',
    ),
    (
        'terra-watch-band-rolls-out-to-health-record',
        'health',
        False,
        52,
        'Terra Watch band rolls continuous vitals into the colony health record',
        'Heart rate, blood oxygen and heat-strain warnings now stream to the record '
        'your medical team reads.',
        'Health Services',
        'The Terra Watch health band is now streaming continuously into the colony '
        'health record. Heart rate, blood oxygen, sleep and step data flow alongside '
        'the heat-strain warnings issued by the weather service — the same alerts '
        'that reach your device during the current warm spell.\n\n'
        'Pairing takes one payment of 50 TRX and lasts for the expedition. Fall '
        'detection opens Terra Chat with your vitals already attached, so the agent '
        'on the other end reads numbers instead of asking for them.\n\n'
        'Health services stress that the band is optional but that the social '
        'security cover assessed from the health record is cheaper for passengers '
        'who keep it paired.',
    ),
    (
        'deep-listening-survey-maps-pelagos-thermocline',
        'science',
        False,
        60,
        'Deep-listening survey maps the Pelagos thermocline to eleven kilometres',
        'Hydrophone arrays record the living light layer and the currents that '
        'shape the midnight ocean.',
        'Pelagos Survey Office',
        'The deep-listening survey has completed its first full pass of the Pelagos '
        'Deep, mapping the thermocline down to eleven kilometres with towed '
        'hydrophone arrays.\n\n'
        'The recordings capture the current shear that drives the nutrient plume '
        'beneath the living-light layer — the same plume the colony\'s fisheries '
        'depend on. Analysts describe the signal as unusually clean for a sea this '
        'deep.\n\n'
        'Processed data will be published to the atlas in stages. The survey office '
        'says the next pass, in the southern basin, begins as the heat wave eases.',
    ),
    (
        'waste-rotation-restored-in-vermilion-steps',
        'civic',
        False,
        72,
        'Waste rotation restored across the Vermilion Steps villages',
        'Collection resumes on the published schedule after the canyon-road repair '
        'closed the depot approach.',
        'Colony Works',
        'Waste collection across the Vermilion Steps villages returns to the '
        'published rotation this week, ending the suspension called during the '
        'canyon-road repair.\n\n'
        'The depot approach — closed while heavy plant moved spoil off the climb — '
        'is open again, and the sector\'s four villages revert to their normal '
        'alternating days. Households that missed two collections during the '
        'closure can leave the overflow at the village point for the first run.\n\n'
        'Works crews will keep the repaired section under observation through the '
        'heat wave, when the canyon road softens fastest in the afternoon.',
    ),
    (
        'agents-scored-by-passengers-in-account-centre',
        'expedition',
        False,
        84,
        'Passengers can now score the agents who answer them in Terra Chat',
        'Ratings from one to five stars flow back to the agent roster and shape '
        'which threads get escalated first.',
        'Terra Chat Operations',
        'Every Novarian can now rate the agent who answered their Terra Chat thread, '
        'straight from the account centre. Scores run from one to five, and a '
        'comment can be attached to explain the stars.\n\n'
        'Ratings feed the agent roster: threads from passengers who have previously '
        'escalated are routed with that history visible, and the operations desk '
        'uses the weekly spread to decide which agents take the complex civic and '
        'medical queues.\n\n'
        'Agents rated outstanding in the first week are listed on the roster page. '
        'Passengers may rate every agent they have actually conversed with — once '
        'each.',
    ),
    (
        'second-bus-line-links-aurelia-and-pelagos-coast',
        'transport',
        False,
        96,
        'Second bus line links Aurelia Basin to the Pelagos coast',
        'The coastal run adds a daytime connection between the first landing site '
        'and the fishing harbours.',
        'Nova Transit',
        'A second scheduled bus line now links the Aurelia Basin — the first landing '
        'site — with the Pelagos coast, adding a daytime connection to the fishing '
        'harbours that previously could only be reached by chartered rail.\n\n'
        'The run stops at every village on the published rotation, and fares are '
        'payable in TerraX with the same QR ticket accepted across the network. '
        'Transit expects the line to take the pressure off coastal road freight '
        'during the tourist peak.\n\n'
        'Timetables are live on the transport page; the board counts down to each '
        'departure in real time, and a fare bought from the board is valid for the '
        'next service on that line.',
    ),
]


def ensure_news():
    """Create the ten seeded dispatches (idempotent).

    Returns the articles that did not exist before this call.
    """
    from .models import NewsItem  # local import avoids circulars

    now = timezone.localtime()
    created = []
    for slug, category, featured, hours_ago, title, summary, source, body in NEWS_ITEMS:
        item, was_created = NewsItem.objects.get_or_create(
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
        if was_created:
            created.append(item)
    return created

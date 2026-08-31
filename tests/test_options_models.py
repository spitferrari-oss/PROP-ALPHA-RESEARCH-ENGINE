import datetime as dt

from prop_alpha.options.gexbot.models import AvailabilityStatus as GexbotAvailabilityStatus
from prop_alpha.options.gexbot.models import Metric as GexbotMetric
from prop_alpha.options.models import (
    AvailabilityStatus,
    LevelType,
    Metric,
    MetricAvailability,
    OptionsLevel,
    OptionsSnapshot,
)


def test_gexbot_models_reexport_the_same_shared_types():
    # options.gexbot.models moved these to options.models in Phase I —
    # anything still importing from the old location must get the exact
    # same class object, not a duplicate.
    assert GexbotAvailabilityStatus is AvailabilityStatus
    assert GexbotMetric is Metric


def test_level_type_covers_extension_29_list():
    expected = {
        "GAMMA_FLIP", "POSITIVE_GAMMA", "NEGATIVE_GAMMA", "MAJOR_GAMMA",
        "DEX_LEVEL", "VANNA_LEVEL", "CHARM_LEVEL",
    }
    assert {t.value for t in LevelType} == expected


def _metric(value):
    return Metric(
        value=value,
        availability=MetricAvailability(
            status=AvailabilityStatus.AVAILABLE, timestamp=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
            source="test", freshness_seconds=0.0,
        ),
    )


def test_options_snapshot_extra_field_defaults_to_none_not_empty_dict():
    snapshot = OptionsSnapshot(
        timestamp=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc), underlying="SPX",
        spot=_metric(4500.0), gex=_metric(1.0), dex=_metric(1.0), gamma_flip=_metric(1.0),
        major_positive_gamma=_metric(1.0), major_negative_gamma=_metric(1.0), vanna=_metric(1.0),
        charm=_metric(1.0), vomma=_metric(1.0), skew=_metric(1.0), options_volume=_metric(1.0),
        open_interest=_metric(1.0),
    )
    assert snapshot.extra is None
    assert snapshot.orderflow_state is None


def test_options_level_construction():
    level = OptionsLevel(
        underlying="SPX", timestamp=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc), strike=4500.0,
        type=LevelType.GAMMA_FLIP, value=4500.0, distance_from_spot=10.0, source="gexbot",
        metric="gamma_flip",
    )
    assert level.strength is None
    assert level.type == LevelType.GAMMA_FLIP

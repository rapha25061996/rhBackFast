"""Unit tests for WorkingDaysService."""
from datetime import date

import pytest

from app.conge_app.constants import DemiJournee
from app.conge_app.services import WorkingDaysService


class TestWorkingDays:
    def test_single_working_day(self):
        # Lundi 2025-01-06 (pas férié en FR)
        day = date(2025, 1, 6)
        count = WorkingDaysService.count_working_days(day, day, country_code="FR", language="fr")
        assert count == 1.0

    def test_single_saturday_not_counted(self):
        # Samedi 2025-01-04
        day = date(2025, 1, 4)
        count = WorkingDaysService.count_working_days(day, day, country_code="FR")
        assert count == 0.0

    def test_full_week_counts_five(self):
        # Lundi 2025-01-06 → Vendredi 2025-01-10
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 6), date(2025, 1, 10), country_code="FR", language="fr"
        )
        assert count == 5.0

    def test_weekend_span_excludes_saturday_sunday(self):
        # Vendredi 2025-01-10 → Lundi 2025-01-13
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 10), date(2025, 1, 13), country_code="FR"
        )
        assert count == 2.0

    def test_french_new_year_excluded(self):
        # 2025-01-01 est férié en France (Jour de l'An)
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 1), date(2025, 1, 3), country_code="FR", language="fr"
        )
        # 01/01 férié, 02 et 03 ouvrés → 2
        assert count == 2.0

    def test_half_day_start_afternoon(self):
        # Lundi au vendredi, mais on commence l'après-midi
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 6),
            date(2025, 1, 10),
            demi_journee_debut=DemiJournee.APRES_MIDI,
            country_code="FR",
        )
        assert count == 4.5

    def test_half_day_end_morning(self):
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 6),
            date(2025, 1, 10),
            demi_journee_fin=DemiJournee.MATIN,
            country_code="FR",
        )
        assert count == 4.5

    def test_half_day_both_ends(self):
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 6),
            date(2025, 1, 10),
            demi_journee_debut=DemiJournee.APRES_MIDI,
            demi_journee_fin=DemiJournee.MATIN,
            country_code="FR",
        )
        assert count == 4.0

    def test_same_day_half_day(self):
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 6),
            date(2025, 1, 6),
            demi_journee_debut=DemiJournee.MATIN,
            demi_journee_fin=DemiJournee.MATIN,
            country_code="FR",
        )
        assert count == 0.5

    def test_unknown_country_returns_zero_holidays(self):
        # Pays inexistant → mapping vide, pas de crash
        holidays_map = WorkingDaysService.get_holidays_for_year(2025, "ZZ", "fr")
        assert holidays_map == {}

    def test_date_fin_before_date_debut_raises(self):
        with pytest.raises(ValueError):
            WorkingDaysService.count_working_days(date(2025, 1, 10), date(2025, 1, 1))

    def test_english_language_works(self):
        # La lib doit accepter la langue en pour au moins un pays supporté.
        count = WorkingDaysService.count_working_days(
            date(2025, 1, 1), date(2025, 1, 3), country_code="US", language="en"
        )
        # 01/01 férié aux US, 02 et 03 ouvrés
        assert count == 2.0

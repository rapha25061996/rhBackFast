"""Service de calcul des jours ouvrés (hors week-ends et jours fériés)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import holidays

from app.conge_app.constants import (
    DEFAULT_COUNTRY_CODE,
    DEFAULT_HOLIDAY_LANGUAGE,
    SUPPORTED_HOLIDAY_LANGUAGES,
    DemiJournee,
)


class WorkingDaysService:
    """Calcule le nombre de jours ouvrés entre deux dates.

    Règles :
    - Les samedis et dimanches sont exclus.
    - Les jours fériés sont récupérés via la lib ``holidays`` (pas de stockage DB).
    - Les demi-journées retirent 0.5 jour (uniquement si le jour concerné est ouvré).
    """

    @staticmethod
    def _sanitize_language(language: Optional[str]) -> Optional[str]:
        if not language:
            return None
        language = language.lower()
        if language not in SUPPORTED_HOLIDAY_LANGUAGES:
            return None
        return language

    @classmethod
    def get_holidays_for_year(
        cls,
        year: int,
        country_code: str = DEFAULT_COUNTRY_CODE,
        language: str = DEFAULT_HOLIDAY_LANGUAGE,
    ) -> dict[date, str]:
        """Retourne le mapping `date -> nom du jour férié` pour une année et un pays.

        La langue n'est utilisée par ``holidays`` que lorsqu'elle est supportée pour
        le pays demandé ; un fallback silencieux sur la langue par défaut du pays
        est appliqué sinon.
        """
        safe_language = cls._sanitize_language(language)
        country = (country_code or DEFAULT_COUNTRY_CODE).upper()
        try:
            country_holidays = holidays.country_holidays(
                country, years=[year], language=safe_language
            )
        except (NotImplementedError, KeyError):
            # Pays inconnu pour la lib : on retourne un mapping vide.
            return {}
        except TypeError:
            # Certaines versions de la lib n'acceptent pas language=None.
            country_holidays = holidays.country_holidays(country, years=[year])
        return {d: name for d, name in country_holidays.items()}

    @classmethod
    def is_working_day(
        cls,
        day: date,
        country_code: str = DEFAULT_COUNTRY_CODE,
        language: str = DEFAULT_HOLIDAY_LANGUAGE,
        holidays_cache: Optional[dict[date, str]] = None,
    ) -> bool:
        """True si le jour est un jour ouvré (pas un week-end, pas un jour férié)."""
        if day.weekday() >= 5:
            return False
        if holidays_cache is None:
            holidays_cache = cls.get_holidays_for_year(day.year, country_code, language)
        return day not in holidays_cache

    @classmethod
    def count_working_days(
        cls,
        date_debut: date,
        date_fin: date,
        demi_journee_debut: Optional[DemiJournee] = None,
        demi_journee_fin: Optional[DemiJournee] = None,
        country_code: str = DEFAULT_COUNTRY_CODE,
        language: str = DEFAULT_HOLIDAY_LANGUAGE,
    ) -> float:
        """Calcule le nombre de jours ouvrés dans l'intervalle [date_debut; date_fin].

        Les demi-journées :
        - ``demi_journee_debut == 'apres-midi'`` → le matin du premier jour n'est pas pris (−0.5).
        - ``demi_journee_fin == 'matin'`` → l'après-midi du dernier jour n'est pas pris (−0.5).

        Une demande qui ne couvre qu'une demi-journée (même jour, demi_journee_debut +
        demi_journee_fin identiques) compte pour 0.5.
        """
        if date_fin < date_debut:
            raise ValueError("date_fin doit être >= date_debut")

        # Cache les jours fériés par année couverte par l'intervalle.
        years = set(range(date_debut.year, date_fin.year + 1))
        holidays_cache: dict[date, str] = {}
        for year in years:
            holidays_cache.update(cls.get_holidays_for_year(year, country_code, language))

        total = 0.0
        current = date_debut
        while current <= date_fin:
            if cls.is_working_day(current, country_code, language, holidays_cache):
                total += 1.0
            current += timedelta(days=1)

        if total == 0:
            return 0.0

        # Ajustements demi-journées (appliqués uniquement si le jour est ouvré).
        premier_ouvre = cls.is_working_day(date_debut, country_code, language, holidays_cache)
        dernier_ouvre = cls.is_working_day(date_fin, country_code, language, holidays_cache)

        if demi_journee_debut == DemiJournee.APRES_MIDI and premier_ouvre:
            total -= 0.5
        if (
            demi_journee_fin == DemiJournee.MATIN
            and dernier_ouvre
            and date_fin != date_debut
        ):
            total -= 0.5
        # Cas demande d'une unique demi-journée (même jour).
        if (
            date_debut == date_fin
            and demi_journee_debut is not None
            and demi_journee_fin is not None
            and demi_journee_debut == demi_journee_fin
            and premier_ouvre
        ):
            total = 0.5

        return max(total, 0.0)

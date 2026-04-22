import holidays

# Exemple pour le Burundi en 2026
burundi_holidays = holidays.Burundi(years=2026)

# Affiche tous les jours fériés
for date, name in burundi_holidays.items():
    print(date, name)

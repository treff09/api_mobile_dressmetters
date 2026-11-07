"""Affichage d'un montant dans la devise de l'atelier (« 15 000 FCFA », « 25,00 € »…)."""
from decimal import Decimal

# code -> (symbole, avant le nombre ?, nombre de décimales)
FORMATS = {
    'XOF': ('FCFA', False, 0), 'XAF': ('FCFA', False, 0), 'GNF': ('FG', False, 0),
    'CDF': ('FC', False, 0), 'EUR': ('€', False, 2), 'CHF': ('CHF', False, 2),
    'MAD': ('DH', False, 2), 'USD': ('$', True, 2), 'GBP': ('£', True, 2),
    'CAD': ('$ CA', False, 2), 'GHS': ('GH₵', True, 2), 'NGN': ('₦', True, 0),
    'KES': ('KSh', True, 0), 'ZAR': ('R', True, 2),
}


def format_montant(montant, code='XOF'):
    symbole, avant, dec = FORMATS.get((code or 'XOF').upper(), (code or 'FCFA', False, 0))
    v = Decimal(str(montant or 0))
    txt = f"{v:,.{dec}f}".replace(',', ' ')
    if dec and not avant:
        txt = txt.replace('.', ',')
    return f"{symbole}{txt}" if avant else f"{txt} {symbole}"

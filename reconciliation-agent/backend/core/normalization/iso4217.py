"""
§7.1 — the ISO 4217 alpha-3 currency codes normalize_currency() validates
against. A hardcoded standard list, not a domain word list (§2.2) — every
reconciliation product needs to know which currency codes exist, regardless
of which rule pack is installed.
"""
from __future__ import annotations

ISO_4217_CODES: frozenset[str] = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN
    BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD
    CAD CDF CHF CLP CNY COP CRC CUP CVE CZK
    DJF DKK DOP DZD
    EGP ERN ETB EUR
    FJD FKP
    GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HTG HUF
    IDR ILS INR IQD IRR ISK
    JMD JOD JPY
    KES KGS KHR KMF KPW KRW KWD KYD KZT
    LAK LBP LKR LRD LSL LYD
    MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN
    NAD NGN NIO NOK NPR NZD
    OMR
    PAB PEN PGK PHP PKR PLN PYG
    QAR
    RON RSD RUB RWF
    SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SYP SZL
    THB TJS TMT TND TOP TRY TTD TWD TZS
    UAH UGX USD UYU UZS
    VES VND VUV
    WST
    XAF XAG XAU XCD XDR XOF XPF
    YER
    ZAR ZMW ZWL
    """.split()
)

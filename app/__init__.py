"""
Msaidizi / Angavu Intelligence — Cloud Backend
=======================================

Intelligence platform for Kenya's informal economy.
Transforms raw transaction data from dukawallahs and mama mbogas
into actionable economic intelligence for FMCG companies, government,
financial institutions, and development organizations.

Architecture:
    On-Device (2GB Android) → Sync API → Data Pipeline → Intelligence APIs
    All data is anonymized with k-anonymity (k≥10) before serving to buyers.
"""

__version__ = "0.1.0"
__title__ = "Msaidizi Backend"

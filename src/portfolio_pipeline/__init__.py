"""Risk-aware portfolio construction and monitoring pipeline.

Execution boundary: this package computes target weights and trade tickets.
It never submits orders anywhere. Wealthsimple Trade's terms of service
prohibit API-based order submission, and IIROC does not permit it for
self-directed Canadian-securities accounts — see docs/methodology.md.
Every decision this pipeline produces is meant to be read by a human and
entered into the brokerage manually.
"""

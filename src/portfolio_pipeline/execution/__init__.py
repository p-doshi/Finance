"""Paper-trade execution only. See `alpaca_paper.py`'s module docstring
for why this is a deliberate, narrowly-scoped exception to the rest of
this project's "decision support, never an order" design — paper-trade
validation (the last item on the original roadmap, docs/methodology.md
§11) specifically requires submitting orders somewhere, and Alpaca's
paper endpoint, backed by fake money, is the standard, free way to do
that without touching a real account."""

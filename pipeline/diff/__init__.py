"""Stage difference and twin comparison, checks V1 and V2 (W13, MASTER_PLAN §7).

text.py     text classes: equal, differs only by anonymization, one is the
            start of the other, differs
compare.py  matching by item number (model.item_no_key) and the field
            comparison; twin report (V1) and stage report (V2)
pdftext.py  how many item titles of a list stand in the page text of a PDF
            that has no reader (T5)
run.py      python -m pipeline.diff.run <items A> <items B> <out json>
pairs.py    python -m pipeline.diff.pairs: all pairs of the organizer data,
            out/diff/*.json and docs/TWINS.md
report.py   docs/TWINS.md from the results of pairs.py

No module here prints or writes a unit price, a total or a price difference:
prices are compared and only "equal / not equal" leaves the code.
"""

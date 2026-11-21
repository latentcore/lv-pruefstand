"""M3: the PDF against its GAEB twin, through pipeline/diff (W13). No comparison code lives here.

The files are read with the readers pipeline.diff.pairs uses and compared with
pipeline.diff.compare in mode "twin", field against field (the T1 and T2
tables of docs/TWINS.md). What leaves this module: counts and percentages.
Never a price, a total or a price difference.
"""
from pipeline.diff import compare, pairs

NOT_AVAILABLE = "pipeline/diff (W13) is not merged yet"
NO_PRICE_PAIR = "no item pair holds a unit price or a total in both files"
NO_PRICE_PAIR_DE = "kein Positionspaar hat in beiden Dateien einen Einheitspreis oder Gesamtbetrag"


class TwinError(RuntimeError):
    """A twin cannot be read; the message says why."""


def available():
    return True


def _key(file_name):
    """The key of pipeline.diff.pairs.FILES for a file name of docs/PREREG.md."""
    for key, (name, _reader, _what) in pairs.FILES.items():
        if name == file_name:
            return key
    raise TwinError("%s is not a file of pipeline.diff.pairs" % file_name)


def read(data, file_name):
    """The item records of one file, read with the reader pipeline.diff.pairs gives it."""
    try:
        return pairs.read_items(data, _key(file_name))
    except pairs.PairsError as error:
        raise TwinError(str(error))


def _tenths(part, whole):
    return (1000 * part) // whole if whole else None


def counts(twin, pdf, gaeb, pdf_items, gaeb_items):
    """The M3 numbers of one pair from two item lists (A = the PDF, B = the GAEB file)."""
    result = compare.compare(pdf_items, gaeb_items, mode="twin", text_map="fields")
    matching, fields = result["matching"], result["fields"]
    entry = {
        "twin": twin, "pdf": pdf, "gaeb": gaeb,
        "items_gaeb": len(compare.positions(gaeb_items)), "items_pdf": len(compare.positions(pdf_items)),
        "items_in_both": matching["both"], "items_only_pdf": len(matching["only_a"]),
        "items_only_gaeb": len(matching["only_b"]),
        "unit_prices_compared": fields["unit_price"]["compared"],
        "unit_prices_equal": fields["unit_price"]["equal"],
        "totals_compared": fields["total"]["compared"], "totals_equal": fields["total"]["equal"],
    }
    entry["items_percent_tenths"] = _tenths(entry["items_in_both"], entry["items_gaeb"])
    shares = [_tenths(entry[key + "_equal"], entry[key + "_compared"])
              for key in ("unit_prices", "totals") if entry[key + "_compared"]]
    entry["prices_measurable"] = bool(shares)
    entry["prices_percent_tenths"] = min(shares) if shares else None
    if not shares:
        entry["prices_reason"], entry["prices_reason_de"] = NO_PRICE_PAIR, NO_PRICE_PAIR_DE
    return entry


def measure(ctx, twin, pdf, gaeb):
    """The M3 numbers of one pair of docs/PREREG.md, read from ctx.data."""
    return counts(twin, pdf, gaeb, read(ctx.data, pdf), read(ctx.data, gaeb))

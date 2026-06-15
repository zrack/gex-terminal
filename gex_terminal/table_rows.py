def arrange_rows(rows, sort_mode, filter_mode, spot, max_volume):
    """Filter then sort the matrix rows."""
    return sort_rows(filter_rows(rows, filter_mode, spot, max_volume), sort_mode)


def filter_rows(rows, filter_mode, spot, max_volume):
    """Filter rows by mode. Never returns empty if input was non-empty."""
    if filter_mode == "near" and spot:
        window = max(spot * 0.01, 1.0)
        subset = [row for row in rows if abs(row["strike"] - spot) <= window]
        return subset or list(rows)
    if filter_mode == "active" and max_volume:
        threshold = max_volume * 0.25
        subset = [row for row in rows if row["volume"] >= threshold]
        return subset or list(rows)
    return list(rows)


def sort_rows(rows, sort_mode):
    if sort_mode == "net":
        return sorted(rows, key=lambda row: abs(row["net_gex"]), reverse=True)
    if sort_mode == "volume":
        return sorted(rows, key=lambda row: row["volume"], reverse=True)
    return sorted(rows, key=lambda row: row["strike"])

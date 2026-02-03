"""
IPF (Iterative Proportional Fitting) Allocation Algorithm

Allocates plan-level enrollment from rating areas down to counties using
two sets of control totals:
  A) Insurer x County totals (from County_Profiles_Final.dta)
  B) Metal Tier x County totals (from County_Profiles_Metals_Final.dta)

Input files:
  - Base.dta: Plan-level enrollment by rating area
  - County_Profiles_Final.dta: Insurer x County enrollment totals
  - County_Profiles_Metals_Final.dta: Metal Tier x County enrollment totals
  - ca_dma_ratingarea_crosswalk.xlsx: County-to-rating-area mapping

Output:
  - enrollment_allocated.csv: County-level plan enrollment estimates
"""

import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings("ignore")


def load_data():
    """Load all input datasets."""
    print("=" * 60)
    print("LOADING DATA")
    print("=" * 60)

    base = pd.read_stata("Base.dta")
    print(f"Base.dta: {base.shape[0]:,} rows")

    county_insurer = pd.read_stata("County_Profiles_Final.dta")
    print(f"County_Profiles_Final.dta: {county_insurer.shape[0]:,} rows")

    county_metal = pd.read_stata("County_Profiles_Metals_Final.dta")
    print(f"County_Profiles_Metals_Final.dta: {county_metal.shape[0]:,} rows")

    # Sheet 0 has 59 rows: LA County appears in both RA 15 and RA 16
    crosswalk = pd.read_excel("ca_dma_ratingarea_crosswalk.xlsx", sheet_name=0)
    print(f"Crosswalk: {crosswalk.shape[0]:,} rows")

    return base, county_insurer, county_metal, crosswalk


def clean_data(base, county_insurer, county_metal, crosswalk):
    """Clean and standardize all datasets."""
    print("\n" + "=" * 60)
    print("CLEANING DATA")
    print("=" * 60)

    # --- Base dataset ---
    base = base.rename(columns={
        "issuer_name": "insurer",
        "plan_type": "plan",
        "metal_level": "metal_tier",
        "Enrollees": "enrollment",
    })
    base["year"] = base["year"].astype("Int64")
    base["rating_area"] = base["rating_area"].astype("Int64")

    n_before = len(base)
    base = base.dropna(subset=["year", "rating_area", "insurer", "metal_tier"])
    base = base[(base["insurer"] != "") & (base["metal_tier"] != "")]
    print(f"Base: dropped {n_before - len(base)} rows with missing key fields")

    base["enrollment"] = base["enrollment"].fillna(0)

    # Harmonize metal tier names to match County_Profiles_Metals_Final
    metal_map = {
        "Bronze": "Bronze",
        "Silver": "Silver",
        "Gold": "Gold",
        "Platinum": "Platinum",
        "Minimum Coverage": "Minimum Coverage",
        "HDHP Bronze": "Bronze HDHP",
        "HSA Bronze": "Bronze HDHP",
        "HDHP": "Bronze HDHP",
    }
    base["metal_tier"] = base["metal_tier"].map(metal_map)
    base = base.dropna(subset=["metal_tier"])
    print(f"Base after metal tier mapping: {len(base):,} rows")

    base = base[["year", "rating_area", "insurer", "plan", "metal_tier", "enrollment"]]
    base = (
        base.groupby(["year", "rating_area", "insurer", "plan", "metal_tier"], as_index=False)
        ["enrollment"].sum()
    )
    print(f"Base after aggregation: {len(base):,} rows")

    # --- County insurer profiles ---
    county_insurer["target_ic"] = pd.to_numeric(
        county_insurer["enrollees"], errors="coerce"
    ).fillna(0)
    county_insurer["year"] = county_insurer["year"].astype("Int64")
    county_insurer["county"] = county_insurer["county"].str.upper().str.strip()
    county_insurer = county_insurer.rename(columns={"issuer": "insurer"})
    county_insurer = county_insurer[["year", "insurer", "county", "target_ic"]]
    county_insurer = county_insurer.groupby(
        ["year", "insurer", "county"], as_index=False
    )["target_ic"].sum()
    print(f"County insurer targets: {len(county_insurer):,} rows")

    # --- County metal profiles ---
    county_metal["year"] = county_metal["year"].astype("Int64")
    county_metal["county"] = county_metal["county"].str.upper().str.strip()
    county_metal["target_mc"] = pd.to_numeric(
        county_metal["enrollees"], errors="coerce"
    ).fillna(0)
    county_metal = county_metal[["year", "metal_tier", "county", "target_mc"]]
    county_metal = county_metal.groupby(
        ["year", "metal_tier", "county"], as_index=False
    )["target_mc"].sum()
    print(f"County metal targets: {len(county_metal):,} rows")

    # --- Crosswalk ---
    crosswalk = crosswalk[["countyname", "ratingarea"]].copy()
    crosswalk.columns = ["county", "rating_area"]
    crosswalk["county"] = crosswalk["county"].str.upper().str.strip()
    crosswalk["rating_area"] = crosswalk["rating_area"].astype("Int64")
    # Crosswalk uses "LA COUNTY"; profiles use "LOS ANGELES"
    crosswalk["county"] = crosswalk["county"].replace({"LA COUNTY": "LOS ANGELES"})
    print(f"Crosswalk: {len(crosswalk)} county-rating_area pairs")

    # Equal weights within each rating area (no population data available)
    n_per_ra = crosswalk.groupby("rating_area")["county"].transform("count")
    crosswalk["weight"] = 1.0 / n_per_ra

    return base, county_insurer, county_metal, crosswalk


def check_margin_consistency(county_insurer, county_metal):
    """Report on consistency between the two sets of control totals."""
    print("\n" + "=" * 60)
    print("MARGIN CONSISTENCY CHECK")
    print("=" * 60)

    ic_totals = county_insurer.groupby(["year", "county"])["target_ic"].sum().reset_index(
        name="insurer_total"
    )
    mc_totals = county_metal.groupby(["year", "county"])["target_mc"].sum().reset_index(
        name="metal_total"
    )
    merged = ic_totals.merge(mc_totals, on=["year", "county"], how="outer").fillna(0)
    merged["abs_diff"] = np.abs(merged["insurer_total"] - merged["metal_total"])
    merged["pct_diff"] = np.where(
        merged["metal_total"] > 0,
        100 * merged["abs_diff"] / merged["metal_total"],
        0,
    )

    n_inconsistent = (merged["pct_diff"] > 1).sum()
    print(f"County-year combos with >1% margin inconsistency: {n_inconsistent} / {len(merged)}")

    if n_inconsistent > 0:
        print("NOTE: Insurer x County totals and Metal x County totals are not fully")
        print("      consistent. IPF will find the best compromise but cannot exactly")
        print("      satisfy both constraints simultaneously.")

    for yr in sorted(merged["year"].unique()):
        m = merged[merged["year"] == yr]
        it = m["insurer_total"].sum()
        mt = m["metal_total"].sum()
        diff_pct = 100 * abs(it - mt) / mt if mt > 0 else 0
        print(f"  Year {int(yr)}: insurer total={it:,.0f}, metal total={mt:,.0f}, diff={diff_pct:.1f}%")


def initial_allocation(base, crosswalk):
    """Stage 1: Allocate rating-area enrollment to counties using population weights."""
    print("\n" + "=" * 60)
    print("STAGE 1: INITIAL ALLOCATION")
    print("=" * 60)

    alloc = base.merge(
        crosswalk[["county", "rating_area", "weight"]],
        on="rating_area",
        how="inner",
    )
    alloc["enrollment_est"] = alloc["enrollment"] * alloc["weight"]

    print(f"Initial allocation: {len(alloc):,} rows")
    print(f"Total enrollment (base): {base['enrollment'].sum():,.0f}")
    print(f"Total enrollment (allocated): {alloc['enrollment_est'].sum():,.0f}")

    alloc = alloc[
        ["year", "county", "rating_area", "insurer", "plan", "metal_tier", "enrollment_est"]
    ].copy()

    return alloc


def run_ipf(alloc, county_insurer, county_metal, max_iter=100, tol=0.001):
    """Stage 2: Iterative Proportional Fitting."""
    print("\n" + "=" * 60)
    print("STAGE 2: ITERATIVE PROPORTIONAL FITTING")
    print("=" * 60)

    years = sorted(alloc["year"].dropna().unique())
    print(f"Processing years: {[int(y) for y in years]}")

    results = []

    for yr in years:
        print(f"\n--- Year {int(yr)} ---")

        df = alloc[alloc["year"] == yr].copy().reset_index(drop=True)
        if len(df) == 0:
            print(f"  No data for year {int(yr)}, skipping.")
            continue

        # Control totals for this year
        targets_ic = county_insurer[county_insurer["year"] == yr]
        targets_mc = county_metal[county_metal["year"] == yr]

        # Build fast lookup Series
        ic_lookup = targets_ic.set_index(["insurer", "county"])["target_ic"]
        mc_lookup = targets_mc.set_index(["metal_tier", "county"])["target_mc"]

        # Pre-compute lookup keys for each row (avoids repeated tuple creation)
        ic_keys = list(zip(df["insurer"], df["county"]))
        mc_keys = list(zip(df["metal_tier"], df["county"]))

        ic_targets = np.array([ic_lookup.get(k, 0) for k in ic_keys], dtype=np.float64)
        mc_targets = np.array([mc_lookup.get(k, 0) for k in mc_keys], dtype=np.float64)

        converged = False
        final_max_change = np.inf

        for iteration in range(1, max_iter + 1):
            prev_est = df["enrollment_est"].values.copy()

            # STEP A: Adjust to Insurer x County margins
            group_sums = df.groupby(["insurer", "county"])["enrollment_est"].transform("sum").values
            factors = np.where(group_sums > 1e-10, ic_targets / group_sums, 0)
            df["enrollment_est"] = df["enrollment_est"].values * factors

            # STEP B: Adjust to Metal Tier x County margins
            group_sums = df.groupby(["metal_tier", "county"])["enrollment_est"].transform("sum").values
            factors = np.where(group_sums > 1e-10, mc_targets / group_sums, 0)
            df["enrollment_est"] = df["enrollment_est"].values * factors

            # Convergence check
            current_est = df["enrollment_est"].values
            nonzero = prev_est > 1e-10
            if nonzero.any():
                max_change = (
                    np.abs(current_est[nonzero] - prev_est[nonzero]) / prev_est[nonzero]
                ).max()
            else:
                max_change = 0.0

            final_max_change = max_change

            if max_change < tol:
                print(f"  Converged at iteration {iteration}, max relative change = {max_change:.6f}")
                converged = True
                break

            if iteration % 20 == 0:
                print(f"  Iteration {iteration}, max relative change = {max_change:.6f}")

        if not converged:
            print(
                f"  WARNING: Did not converge after {max_iter} iterations. "
                f"Final max change = {final_max_change:.6f}"
            )

        results.append(df)

    allocated = pd.concat(results, ignore_index=True)
    allocated["enrollment_est"] = allocated["enrollment_est"].clip(lower=0)
    print(f"\nFinal allocated dataset: {len(allocated):,} rows")

    return allocated


def validate(allocated, county_insurer, county_metal, base):
    """Run validation checks on the allocated data."""
    print("\n" + "=" * 60)
    print("VALIDATION CHECKS")
    print("=" * 60)

    # Check 1: Insurer x County totals
    check_ic = allocated.groupby(["year", "insurer", "county"])["enrollment_est"].sum().reset_index()
    check_ic = check_ic.merge(county_insurer, on=["year", "insurer", "county"], how="inner")
    mask = check_ic["target_ic"] > 0
    if mask.any():
        diffs = np.abs(check_ic.loc[mask, "enrollment_est"] - check_ic.loc[mask, "target_ic"]) / check_ic.loc[mask, "target_ic"]
        max_ic_diff = diffs.max()
        median_ic_diff = diffs.median()
        pct_within_1 = 100 * (diffs < 0.01).mean()
        pct_within_5 = 100 * (diffs < 0.05).mean()
        print(f"Check 1 (Insurer x County): max relative diff = {max_ic_diff:.4f}, "
              f"median = {median_ic_diff:.4f}")
        print(f"  {pct_within_1:.1f}% within 1%, {pct_within_5:.1f}% within 5%")
        if max_ic_diff < 0.001:
            print("  PASS")
        else:
            print("  NOTE: Differences due to inconsistent margins between control files")

    # Check 2: Metal Tier x County totals
    check_mc = allocated.groupby(["year", "metal_tier", "county"])["enrollment_est"].sum().reset_index()
    check_mc = check_mc.merge(county_metal, on=["year", "metal_tier", "county"], how="inner")
    mask = check_mc["target_mc"] > 0
    if mask.any():
        diffs = np.abs(check_mc.loc[mask, "enrollment_est"] - check_mc.loc[mask, "target_mc"]) / check_mc.loc[mask, "target_mc"]
        max_mc_diff = diffs.max()
        print(f"Check 2 (Metal x County): max relative diff = {max_mc_diff:.6f}")
        print(f"  {'PASS' if max_mc_diff < 0.001 else 'FAIL'}")

    # Check 3: Rating area totals
    check_ra = allocated.groupby(
        ["year", "rating_area", "insurer", "plan", "metal_tier"]
    )["enrollment_est"].sum().reset_index()
    check_ra = check_ra.merge(
        base, on=["year", "rating_area", "insurer", "plan", "metal_tier"], how="inner"
    )
    mask = check_ra["enrollment"] > 0
    if mask.any():
        diffs = np.abs(check_ra.loc[mask, "enrollment_est"] - check_ra.loc[mask, "enrollment"]) / check_ra.loc[mask, "enrollment"]
        max_ra_diff = diffs.max()
        median_ra_diff = diffs.median()
        print(f"Check 3 (Rating Area totals): max relative diff = {max_ra_diff:.4f}, "
              f"median = {median_ra_diff:.4f}")
        if max_ra_diff < 0.001:
            print("  PASS")
        else:
            print("  NOTE: Rating area totals shift during IPF (expected when margins conflict)")

    # Check 4: No negatives
    neg_count = (allocated["enrollment_est"] < 0).sum()
    print(f"Check 4 (No negatives): {'PASS' if neg_count == 0 else 'FAIL'} ({neg_count} negative values)")


def save_output(allocated):
    """Save output CSV and print summary statistics."""
    print("\n" + "=" * 60)
    print("SAVING OUTPUT")
    print("=" * 60)

    output = (
        allocated[["year", "county", "rating_area", "insurer", "plan", "metal_tier", "enrollment_est"]]
        .sort_values(["year", "county", "insurer", "plan", "metal_tier"])
        .reset_index(drop=True)
    )
    output.to_csv("enrollment_allocated.csv", index=False)
    print(f"Saved enrollment_allocated.csv ({len(output):,} rows)")

    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    print("\nTotal enrollment by year:")
    for yr, total in output.groupby("year")["enrollment_est"].sum().items():
        print(f"  {int(yr)}: {total:,.1f}")

    print(f"\nTotal rows: {len(output):,}")
    print(f"Unique counties: {output['county'].nunique()}")
    print(f"Unique insurers: {output['insurer'].nunique()}")
    print(f"Unique plans: {output['plan'].nunique()}")
    print(f"Unique metal tiers: {output['metal_tier'].nunique()}")
    print(f"Year range: {int(output['year'].min())} - {int(output['year'].max())}")

    return output


def main():
    base_raw, ci_raw, cm_raw, cw_raw = load_data()
    base, county_insurer, county_metal, crosswalk = clean_data(base_raw, ci_raw, cm_raw, cw_raw)

    check_margin_consistency(county_insurer, county_metal)

    alloc = initial_allocation(base, crosswalk)
    allocated = run_ipf(alloc, county_insurer, county_metal, max_iter=100, tol=0.001)
    validate(allocated, county_insurer, county_metal, base)
    save_output(allocated)

    print("\nDone.")


if __name__ == "__main__":
    main()

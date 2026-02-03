# Methodology Memo: County-Level Enrollment Estimation Using Iterative Proportional Fitting

**Date:** February 2026
**Subject:** Allocating ACA Plan Enrollment from Rating Areas to Counties

---

## Executive Summary

This memo describes the methodology used to estimate county-level enrollment for individual health insurance plans in California's ACA marketplace. The challenge is that enrollment data is reported at the **rating area level** (19 geographic regions), but analysis often requires **county-level** estimates (58 counties). We use Iterative Proportional Fitting (IPF) to allocate rating-area enrollment down to counties while ensuring consistency with known county-level totals.

---

## Problem Statement

California's ACA marketplace reports plan enrollment by **rating area**—geographic regions used for premium pricing that often span multiple counties. For example, Rating Area 1 covers 22 rural northern California counties. However, many policy and market analyses require county-level enrollment data.

We have three sources of information:
1. **Plan-level enrollment by rating area** (detailed but geographically coarse)
2. **Insurer totals by county** (county-level but no plan detail)
3. **Metal tier totals by county** (county-level but no insurer detail)

The goal is to combine these sources to produce plan-level enrollment estimates at the county level.

---

## Data Inputs

| File | Granularity | Key Fields |
|------|-------------|------------|
| Base.dta | Plan × Rating Area × Year | insurer, plan, metal tier, enrollment |
| County_Profiles_Final.dta | Insurer × County × Year | insurer, county, enrollment |
| County_Profiles_Metals_Final.dta | Metal Tier × County × Year | metal tier, county, enrollment |
| ca_dma_ratingarea_crosswalk.xlsx | County → Rating Area | county, rating area |

---

## Methodology: Iterative Proportional Fitting

### What is IPF?

Iterative Proportional Fitting (also known as "raking" or the "RAS algorithm") is a statistical technique for adjusting a matrix of values so that its row and column totals match known marginal totals. It was developed in the 1940s and is widely used in:

- Census data adjustment
- Survey weighting
- Transportation modeling
- Market research

The method works by alternately scaling rows and columns until the matrix converges to a solution that satisfies both sets of marginal constraints (or gets as close as possible when constraints are inconsistent).

### Application to Enrollment Allocation

We treat the problem as fitting a three-dimensional array (county × insurer × metal tier) to two sets of known marginals:

- **Constraint A:** Insurer × County totals must match County_Profiles_Final
- **Constraint B:** Metal Tier × County totals must match County_Profiles_Metals_Final

### Algorithm Steps

#### Stage 1: Initial Allocation

For each plan in the base data:
1. Identify all counties within the plan's rating area
2. Allocate enrollment proportionally across counties using equal weights (population weights unavailable)

For example, if a plan has 3,000 enrollees in Rating Area 9 (which contains Santa Cruz, Monterey, and San Benito counties), each county initially receives 1,000 enrollees.

#### Stage 2: Iterative Proportional Fitting

Repeat until convergence (or maximum 100 iterations):

**Step A — Adjust to Insurer × County margins:**
```
For each (insurer, county) combination:
    current_total = sum of all plan enrollments for this insurer in this county
    target_total = value from County_Profiles_Final
    adjustment_factor = target_total / current_total
    Scale all plan enrollments by adjustment_factor
```

**Step B — Adjust to Metal Tier × County margins:**
```
For each (metal_tier, county) combination:
    current_total = sum of all plan enrollments for this metal tier in this county
    target_total = value from County_Profiles_Metals_Final
    adjustment_factor = target_total / current_total
    Scale all plan enrollments by adjustment_factor
```

**Convergence check:**
```
Calculate maximum relative change from previous iteration
If max_change < 0.001, stop (converged)
```

---

## Convergence Properties

IPF is guaranteed to converge when:
1. A feasible solution exists (both sets of marginals are internally consistent)
2. The initial matrix has positive values in all cells that should be non-zero

In practice, marginals from different data sources may have small inconsistencies. IPF will converge to the best compromise solution, with the last-applied constraint being exactly satisfied.

In our implementation:
- Metal Tier × County margins are exactly satisfied (last constraint applied)
- Insurer × County margins are approximately satisfied
- The algorithm converges in 5-6 iterations per year

---

## Results Summary

| Metric | Value |
|--------|-------|
| Output rows | 8,465 |
| Years covered | 2014–2019 |
| Counties | 58 |
| Insurers | 13 |
| Plan types | 6 |
| Metal tiers | 6 |
| Iterations to converge | 5–6 per year |

### Constraint Satisfaction

| Check | Result |
|-------|--------|
| Metal × County totals | Exact match |
| Insurer × County totals | 88.8% within 1%, 96.2% within 5% |
| No negative values | Pass |

---

## Limitations and Caveats

1. **Equal county weights:** The crosswalk lacks population data, so we use equal weights for initial allocation within rating areas. This means the initial allocation may not reflect true population distribution, though IPF corrects for this to the extent possible given the constraints.

2. **Plan-type distribution assumed proportional:** The allocation assumes that the distribution of plan types (HMO, PPO, etc.) within an insurer-metal tier combination is the same across counties in a rating area. This assumption cannot be validated with available data.

3. **Small cell instability:** For combinations with very small enrollment counts, estimates may be less reliable.

4. **Margin inconsistencies:** Small discrepancies between the two control total files (typically <1%) mean both constraints cannot be exactly satisfied simultaneously.

---

## Output File

**enrollment_allocated.csv**

| Column | Description |
|--------|-------------|
| year | Calendar year |
| county | California county name |
| rating_area | ACA rating area (1-19) |
| insurer | Insurance company name |
| plan | Plan type (HMO, PPO, EPO, etc.) |
| metal_tier | ACA metal tier (Bronze, Silver, Gold, Platinum, Minimum Coverage, Bronze HDHP) |
| enrollment_est | Estimated enrollment count |

---

## References

- Deming, W.E. & Stephan, F.F. (1940). "On a Least Squares Adjustment of a Sampled Frequency Table When the Expected Marginal Totals are Known." *Annals of Mathematical Statistics*.
- Bishop, Y.M.M., Fienberg, S.E., & Holland, P.W. (1975). *Discrete Multivariate Analysis: Theory and Practice*. MIT Press.
- California Department of Insurance, Rate Filing Data
- Covered California Enrollment Reports

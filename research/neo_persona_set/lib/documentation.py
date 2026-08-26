"""Column notes and formula reference for the exported workbook.

Kept separate from the export code so the wording can be reviewed as prose rather than read out of
formatting logic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Column notes — attached as cell comments on each sheet's header row.
# ---------------------------------------------------------------------------

PERSONAS_NOTES: dict[str, str] = {
    "Persona ID": (
        "Stable identifier for this persona, NEO_01 to NEO_15.\n\n"
        "Ordering is accept first, then unsure, then reject; within each group the personas run "
        "from the strongest score to the weakest. The number carries no other meaning."
    ),
    "Name": (
        "LLM-INFERRED. Not from Census data.\n\n"
        "Invented to make the persona readable. Names were generated with an exclusion list so no "
        "two personas share one, and the spread of backgrounds reflects Southern California."
    ),
    "Headline": "LLM-INFERRED. A one-line characterisation of the person, under 60 characters.",
    "Occupation": (
        "LLM-INFERRED, but constrained by grounded fields.\n\n"
        "The model was required to pick a job consistent with the household's real income bracket "
        "and work mode. It is a plausible occupation, not a Census-reported one — ACS occupation "
        "codes were not used."
    ),
    "Segment": (
        "RULE-DERIVED from the persona's own attributes — see derive_segment() in "
        "04_select_personas.py.\n\n"
        "Assigned by the combination of work mode, household size, age, and income. This replaces "
        "the app's current approach, which picks a segment label from the loop index rather than "
        "from the data."
    ),
    "Likely Response": (
        "RULE-DERIVED. One of accept, unsure, or reject.\n\n"
        "Produced by the transparent scoring function in lib/rejection.py, using ACS fields only — "
        "no LLM judgement. Every label is reproducible from the persona's Census attributes.\n\n"
        "Two hard guards sit above the score: a household with no positive income is not scorable "
        "at all, and a price above 30% of income cannot be 'accept' unless the household is "
        "high-income. See the Formulas sheet."
    ),
    "Score": (
        "RULE-DERIVED. The additive score behind Likely Response.\n\n"
        "Sum of the weights of every rule that fired. accept at >= +2.0, reject at <= -1.0, "
        "otherwise unsure. The full weight table and worked examples are on the Formulas sheet."
    ),
    "Age": (
        "ACS-GROUNDED. Exact age of the household reference person (ACS variable AGEP).\n\n"
        "Taken from the real donor household, not rounded or invented."
    ),
    "Household": (
        "ACS-GROUNDED. Number of people in the household (ACS variable NP).\n\n"
        "From the real donor household."
    ),
    "Household Income": (
        "ACS-GROUNDED. Total annual household income in constant dollars.\n\n"
        "ACS variable HINCP multiplied by ADJINC. The adjustment is essential: the 2024 5-Year file "
        "spans five income years with factors from 1.015250 to 1.222017, so skipping it misstates "
        "income by up to 22%. See the Formulas sheet."
    ),
    "Income Bracket": (
        "ACS-GROUNDED. Bucketed adjusted income.\n\n"
        "low = under $35k; middle = $35k-$75k; upper_middle = $75k-$150k; high = $150k+.\n"
        "Bucket boundaries match the app's existing vocabulary so this output stays "
        "schema-compatible with it."
    ),
    "$23k as % of Income": (
        "DERIVED from grounded fields. The Tahoe Mini's $23,000 price divided by annual household "
        "income, as a percentage.\n\n"
        "The single strongest driver of Likely Response. Values above 100% mean the product costs "
        "more than the household earns in a year.\n\n"
        "Households with zero or negative income yield no value here and were excluded from the "
        "persona pool, rather than being allowed to default into 'accept'."
    ),
    "Housing Cost Burden %": (
        "ACS-GROUNDED. Selected monthly owner costs as a percentage of household income "
        "(ACS variable OCPIP).\n\n"
        "Above 30% is the standard federal definition of cost-burdened; above 50% is severely "
        "cost-burdened. This is why some high-income personas still decline — they are already "
        "stretched by their existing mortgage."
    ),
    "Work Mode": (
        "ACS-GROUNDED. Derived from ACS variable JWTRNS (means of transportation to work).\n\n"
        "remote_friendly = worked from home (JWTRNS 11); commute_based = any other travel mode; "
        "not_working_or_unknown = blank, meaning not in the labour force or not currently working.\n\n"
        "Matters here because a backyard studio has a concrete daily use for a remote worker."
    ),
    "Home Type": (
        "ACS-GROUNDED. Derived from ACS variable BLD (units in structure).\n\n"
        "All 15 personas are 'detached', because a detached single-family house is our proxy for "
        "the survey's outdoor-space screener (S3). ACS has no yard variable, so this is the "
        "pipeline's largest assumption.\n\n"
        "Note: this recode uses the official PUMS dictionary and differs from the app's current "
        "mapping, which misclassifies mobile homes and attached houses."
    ),
    "PUMA": (
        "ACS-GROUNDED. Public Use Microdata Area — the Census geography this household lives in.\n\n"
        "One of 151 Southern California PUMAs, derived from the official Census tract-to-PUMA "
        "crosswalk rather than a hardcoded list. Covers Los Angeles, Orange, San Diego, Riverside, "
        "San Bernardino, and Ventura counties."
    ),
    "Quote": (
        "LLM-INFERRED. A single sentence in the persona's own voice.\n\n"
        "Written to match the fixed Likely Response — a rejecting persona genuinely declines rather "
        "than being softened into enthusiasm. Not a real survey response; no real respondent said "
        "this."
    ),
}

REJECTORS_NOTES: dict[str, str] = {
    "Persona ID": "Identifier matching the Personas sheet.",
    "Name": "LLM-INFERRED name. See the Personas sheet for the same column.",
    "Age": "ACS-GROUNDED. Exact age of the household reference person (AGEP).",
    "Income": (
        "ACS-GROUNDED. Annual household income in constant dollars (HINCP x ADJINC)."
    ),
    "$23k as % of Income": (
        "DERIVED. $23,000 divided by annual household income.\n\n"
        "For every persona on this sheet the value is high enough that the price rule fires "
        "negatively. Above 100% means the product costs more than a year of household income."
    ),
    "Housing Cost Burden %": (
        "ACS-GROUNDED (OCPIP). Existing monthly owner costs as a share of income.\n\n"
        "Above 30% is cost-burdened, above 50% severely so. Several rejectors decline on this "
        "alone: they are not poor, they are already over-committed to their existing mortgage."
    ),
    "Why they decline": (
        "RULE-DERIVED. The specific rules that fired negatively for this persona.\n\n"
        "Each line is reproducible from the Census fields to its left. Because the survey screener "
        "terminates anyone without outdoor space, everyone here PASSED screening and still says no "
        "— so these objections are about cost and value, never about lacking a yard."
    ),
}

MODEL_NOTES: dict[str, str] = {
    "Model": (
        "Which persona-generation method was tested.\n\n"
        "M0 reproduces what the app does today (independent draws per attribute). M1 resamples real "
        "households and is the fidelity ceiling, not a deployable candidate. M2, M3, and M4 are "
        "genuine generative models. M4 was selected."
    ),
    "Marginal TVD": (
        "Mean total variation distance across each attribute's one-dimensional distribution. "
        "Lower is better; 0 is perfect.\n\n"
        "READ THIS FIRST: every model scores about the same here (0.0037-0.0040). All five match "
        "the marginals essentially perfectly. That is the point — the differences between models "
        "live entirely in the joint structure measured by the next three columns."
    ),
    "Association Error": (
        "Frobenius distance between the real and synthetic Cramer's V matrices. Lower is better; "
        "0 is perfect.\n\n"
        "The headline metric. It measures whether attributes are correlated the way they really "
        "are — whether income actually tracks tenure and age the way it does in Southern "
        "California.\n\n"
        "This is the column that exposes independent sampling: a model drawing each attribute "
        "separately produces a near-zero association matrix no matter what the real one looks "
        "like, which is why M0 scores 1.2047 against M4's 0.0897."
    ),
    "Purchase-Triple TVD": (
        "Total variation distance over the joint distribution of income x tenure x home type. "
        "Lower is better.\n\n"
        "The combination that decides whether a household can actually buy a $23,000 backyard "
        "studio, so it is the most decision-relevant fidelity number in this table."
    ),
    "Full Joint TVD": (
        "Total variation distance over the full cross-tabulation of all six modelled attributes. "
        "Lower is better.\n\n"
        "The strictest test. Absolute values are inflated for every model by finite-sample noise "
        "across many cells, so compare models against each other rather than against zero."
    ),
    "C2ST Gap": (
        "Classifier two-sample test. A gradient-boosted classifier is trained to tell real "
        "households from synthetic ones; this reports |AUC - 0.5|. Lower is better; 0 means the "
        "classifier cannot distinguish them at all.\n\n"
        "A holistic check that catches structure the other metrics might miss."
    ),
    "Held-out LogLik": (
        "Mean weighted log-likelihood the model assigns to real held-out households. "
        "HIGHER is better — the opposite direction from every other numeric column here.\n\n"
        "Blank for models that do not define a likelihood (weighted bootstrap and Gaussian copula)."
    ),
    "Composite Rank": (
        "Mean of the model's rank across the five fidelity metrics. Lower is better; 1.0 would be "
        "first place on every metric.\n\n"
        "Used only to order this table. The actual selection rule was to take the best genuinely "
        "generative model, which excludes the bootstrap ceiling."
    ),
    "Fit Seconds": (
        "Mean wall-clock time to fit the model once, in seconds.\n\n"
        "Included for the app-integration decision. The selected latent class model is by far the "
        "slowest to fit (roughly 40s on 268k households), so it should be fitted once and cached "
        "rather than refitted per request."
    ),
}

DETAIL_NOTES: dict[str, str] = {
    "Headline": "LLM-INFERRED. One-line characterisation.",
    "Occupation": "LLM-INFERRED, constrained to be consistent with the grounded income and work mode.",
    "Segment": "RULE-DERIVED from the persona's own attribute combination.",
    "Census profile": (
        "ACS-GROUNDED. Every value on this line comes from a real Census household record: exact "
        "age, household size, adjusted annual income, tenure, structure type, work mode, and PUMA."
    ),
    "$23,000 is": (
        "DERIVED. The Tahoe Mini price as a share of this household's annual income. The strongest "
        "single driver of the likely response."
    ),
    "Backstory": "LLM-INFERRED. Written to fit the grounded profile; never contradicts it.",
    "Typical weekday": "LLM-INFERRED. Consistent with the grounded work mode and household size.",
    "Motivations": "LLM-INFERRED. What this person wants from their property.",
    "Objections": "LLM-INFERRED. Hesitations specific to this product, not generic ones.",
    "Reaction to Tahoe Mini": (
        "LLM-INFERRED narrative, but the STANCE is fixed by the rule-derived likely response. A "
        "rejecting persona genuinely declines here."
    ),
    "Quote": "LLM-INFERRED. Not a real survey response.",
    "Why this response": "RULE-DERIVED. The additive score; see the Formulas sheet for the weights.",
    "  Factors in favour": "RULE-DERIVED. Rules that fired positively, each traceable to a Census field.",
    "  Factors against": "RULE-DERIVED. Rules that fired negatively, each traceable to a Census field.",
}

FIELD_VALUE_HEADERS = {
    "Field": (
        "The name of the attribute described on this row.\n\n"
        "Hover any field name below for a note on what it means and whether it is Census-grounded, "
        "rule-derived, or written by the language model."
    ),
    "Value": "The value of that attribute for this persona.",
    "Item": "The name of the provenance item described on this row.",
    "Detail": "The value, source, or explanation for that item.",
}


# ---------------------------------------------------------------------------
# Formula reference — one block per formula on the Formulas sheet.
# ---------------------------------------------------------------------------

FORMULAS: list[dict] = [
    {
        "name": "Income adjustment to constant dollars",
        "purpose": "Make incomes from different survey years comparable.",
        "formula": "adjusted_income  =  HINCP  x  (ADJINC / 1,000,000)",
        "symbols": (
            "HINCP   = household income as reported, in the dollars of its own survey year\n"
            "ADJINC  = Census adjustment factor, stored as an integer with 6 implied decimals"
        ),
        "reading": (
            "Mandatory for any multi-year file. The 2024 5-Year data contains five different "
            "ADJINC values, from 1,015,250 to 1,222,017 — a spread of 22%. Comparing raw HINCP "
            "across years would silently misstate income by that much."
        ),
        "example": (
            "A household reporting HINCP = 100,000 with ADJINC = 1,222,017:\n"
            "    100,000 x (1,222,017 / 1,000,000)  =  $122,201.70 in constant dollars"
        ),
        "code": "lib/recode.py -> adjust_income()",
    },
    {
        "name": "Price-to-income ratio",
        "purpose": "Express the Tahoe Mini's price as a share of what the household earns in a year.",
        "formula": "price_to_income  =  23,000  /  adjusted_income        (undefined if income <= 0)",
        "symbols": "23,000 = Tahoe Mini price, delivered and installed",
        "reading": (
            "The strongest single predictor of whether a persona accepts. Under 10% is comfortable; "
            "over 40% makes the purchase implausible for most households.\n\n"
            "Deliberately UNDEFINED rather than infinite for non-positive income. Households "
            "reporting zero or negative income are a real ACS category (business losses), but they "
            "cannot be scored for affordability, so they are dropped from the persona pool. Letting "
            "them through would have produced $0-income households labelled as likely buyers."
        ),
        "example": (
            "Dolores Perez (NEO_15), adjusted income $21,409:\n"
            "    23,000 / 21,409  =  1.074  =  107.4% of annual household income"
        ),
        "code": "lib/recode.py -> price_to_income_ratio()",
    },
    {
        "name": "Weighted distribution",
        "purpose": "Turn survey records into population shares.",
        "formula": "p(category)  =  ( sum of WGTP over rows in that category )  /  ( sum of WGTP over all rows )",
        "symbols": (
            "WGTP = ACS housing unit weight — how many real households this record represents"
        ),
        "reading": (
            "Every share, total, and metric in this workbook is weighted. Counting records instead "
            "of weighting them would describe the ACS sample rather than the actual population of "
            "Southern California."
        ),
        "example": (
            "356,974 sampled households carry weights summing to 7,399,942 — the estimated number "
            "of occupied households across the six counties."
        ),
        "code": "lib/metrics.py -> weighted_distribution()",
    },
    {
        "name": "Total Variation Distance (TVD)",
        "purpose": "Measure how far a synthetic distribution sits from the real one.",
        "formula": "TVD(p, q)  =  0.5  x  SUM over all categories i of  | p(i) - q(i) |",
        "symbols": (
            "p(i) = real weighted share of category i, from held-out households\n"
            "q(i) = synthetic share of category i, from generated households"
        ),
        "reading": (
            "Ranges 0 to 1. Lower is better. 0 means the distributions are identical; 1 means they "
            "have no overlap at all.\n\n"
            "Interpretable as the largest possible error in any probability estimate you could make "
            "from the synthetic data."
        ),
        "example": (
            "Real shares are owner 53%, renter 45%, other 2%.\n"
            "Synthetic shares are      owner 50%, renter 48%, other 2%.\n"
            "    TVD = 0.5 x (|0.53-0.50| + |0.45-0.48| + |0.02-0.02|)\n"
            "        = 0.5 x (0.03 + 0.03 + 0.00)  =  0.03"
        ),
        "code": "lib/metrics.py -> total_variation_distance()",
    },
    {
        "name": "Marginal TVD (the 'Marginal TVD' column)",
        "purpose": "Average one-dimensional accuracy across all six attributes.",
        "formula": "marginal_TVD  =  ( 1 / 6 )  x  SUM over the 6 attributes of  TVD( real_a , synthetic_a )",
        "symbols": (
            "The six attributes: age_bucket, income_bucket, household_size_bucket, ownership, "
            "home_type, work_mode"
        ),
        "reading": (
            "All five models score 0.0037-0.0040 here — effectively tied. Matching marginals is "
            "easy, and every model does it.\n\n"
            "This is the most important thing to understand about the comparison: because marginal "
            "accuracy does not separate the models, any difference between them must be measured "
            "in the joint structure."
        ),
        "example": "Selected model M4 scored 0.0037; the app's current method M0 scored 0.0040.",
        "code": "lib/metrics.py -> marginal_tvd()",
    },
    {
        "name": "Cramer's V (with Bergsma bias correction)",
        "purpose": "Measure how strongly two categorical attributes are associated.",
        "formula": (
            "chi2      =  SUM over cells of  ( observed - expected )^2 / expected\n"
            "expected  =  ( row total x column total ) / grand total\n"
            "phi2      =  chi2 / n\n\n"
            "Bergsma correction, which removes the inflation that many categories cause:\n"
            "    phi2~  =  max( 0 ,  phi2 - ( (k-1)(r-1) / (n-1) ) )\n"
            "    r~     =  r - (r-1)^2 / (n-1)\n"
            "    k~     =  k - (k-1)^2 / (n-1)\n\n"
            "V  =  sqrt(  phi2~  /  min( r~ - 1 , k~ - 1 )  )"
        ),
        "symbols": (
            "r = number of rows (categories of attribute A)\n"
            "k = number of columns (categories of attribute B)\n"
            "n = total weight in the table, not the raw record count"
        ),
        "reading": (
            "Ranges 0 to 1. 0 means the two attributes are independent; 1 means one perfectly "
            "determines the other.\n\n"
            "The correction matters because an uncorrected V rises with the number of categories "
            "even when nothing is actually associated, which would flatter attributes with many "
            "buckets."
        ),
        "example": (
            "In the real data, income_bucket and ownership are meaningfully associated — higher "
            "income households own more often. A model that draws the two independently produces "
            "V close to 0 for that pair, and the gap becomes the association error below."
        ),
        "code": "lib/metrics.py -> cramers_v()",
    },
    {
        "name": "Association Error (the headline metric)",
        "purpose": "Measure whether the synthetic population preserves real correlations.",
        "formula": (
            "Build one Cramer's V matrix for the real data and one for the synthetic data, each\n"
            "6 x 6 with V for every attribute pair. Then:\n\n"
            "    association_error  =  sqrt(  SUM over all pairs (i,j) of  ( V_real(i,j) - V_syn(i,j) )^2  )\n\n"
            "which is the Frobenius norm of the difference between the two matrices."
        ),
        "symbols": (
            "V_real(i,j) = association between attributes i and j in held-out real households\n"
            "V_syn(i,j)  = the same association in the generated households"
        ),
        "reading": (
            "Lower is better; 0 means every pairwise association was reproduced exactly.\n\n"
            "This is the metric that exposes independent sampling. A model that draws each "
            "attribute from its own marginal produces V_syn ~ 0 for every pair, so its error "
            "becomes roughly the size of the entire real association matrix — regardless of how "
            "well it matched the marginals."
        ),
        "example": (
            "M0 independent marginals (what the app does today):  1.2047\n"
            "M4 latent class (selected):                          0.0897\n"
            "M1 weighted bootstrap (ceiling, copies real rows):   0.0209\n\n"
            "Improvement of M4 over M0:  (1.2047 - 0.0897) / 1.2047  =  92.6% lower error."
        ),
        "code": "lib/metrics.py -> pairwise_association_error()",
    },
    {
        "name": "Joint TVD (Purchase-Triple and Full Joint columns)",
        "purpose": "Compare whole combinations of attributes, not one attribute at a time.",
        "formula": (
            "Concatenate the chosen attributes into a single compound category per household,\n"
            "then apply TVD to those compound categories:\n\n"
            "    joint_TVD  =  0.5  x  SUM over compound categories c of  | p(c) - q(c) |\n\n"
            "Purchase-Triple uses:  income_bucket x ownership x home_type\n"
            "Full Joint uses:       all six attributes together"
        ),
        "symbols": "c = one specific combination, e.g. 'upper_middle | owner | detached'",
        "reading": (
            "Lower is better. This is the direct test of whether realistic KINDS of household "
            "appear at realistic rates.\n\n"
            "Full Joint values are inflated for every model by finite-sample noise across many "
            "combinations, so read them relatively rather than as absolute error."
        ),
        "example": (
            "On the purchase triple:\n"
            "    M0 (app today)      0.3249\n"
            "    M4 (selected)       0.0178\n"
            "    M1 (ceiling)        0.0145\n\n"
            "M4 is 18x closer to the truth than M0, and nearly at the ceiling set by copying real "
            "households."
        ),
        "code": "lib/metrics.py -> joint_tvd()",
    },
    {
        "name": "Classifier Two-Sample Test (C2ST Gap)",
        "purpose": "Ask whether a machine-learning model can tell real households from synthetic ones.",
        "formula": (
            "1. Resample real households in proportion to WGTP so both sides are unweighted and\n"
            "   equally sized.\n"
            "2. Label real = 1, synthetic = 0.\n"
            "3. Train a gradient-boosted classifier on 70% and score AUC on the held-out 30%.\n\n"
            "    C2ST_gap  =  | AUC - 0.5 |"
        ),
        "symbols": (
            "AUC = area under the ROC curve. 0.5 means the classifier is guessing; 1.0 means it "
            "separates the two sets perfectly."
        ),
        "reading": (
            "Reported as the distance from 0.5 so that, like every other fidelity column, lower is "
            "better. 0 means the synthetic households are statistically indistinguishable from real "
            "ones.\n\n"
            "The most holistic check in the table: it can detect structure that the hand-picked "
            "metrics above were not designed to look for."
        ),
        "example": (
            "M0 scores 0.3134, meaning AUC ~ 0.81 — the classifier spots synthetic households "
            "easily. M4 scores 0.0617 (AUC ~ 0.56), close to guessing."
        ),
        "code": "lib/metrics.py -> c2st_auc()",
    },
    {
        "name": "M0 — Independent marginals (the baseline, and what the app does today)",
        "purpose": "Reproduce the app's current persona generation so it can be measured.",
        "formula": (
            "P(age, income, household_size, ownership, home_type, work_mode)\n"
            "        =  P(age) x P(income) x P(household_size) x P(ownership) x P(home_type) x P(work_mode)\n\n"
            "Each attribute is drawn from its own weighted marginal, independently of the others."
        ),
        "symbols": "Each P(.) is a weighted marginal built with the weighted-distribution formula above.",
        "reading": (
            "This is a faithful reproduction of the app's live behaviour: "
            "_sample_grounded_traits_with_rng() makes four separate weighted draws, so the joint "
            "distribution it produces is exactly the product of its marginals.\n\n"
            "The consequence is structural, not a tuning problem. By construction the model cannot "
            "represent any correlation at all, which is why it finishes last on every joint metric "
            "while matching the marginals perfectly."
        ),
        "example": (
            "It will happily generate a 22-year-old, high-income, 6-person, mobile-home-owning "
            "remote worker at the rate implied by multiplying those four independent probabilities "
            "— a combination that is far rarer in reality."
        ),
        "code": "lib/models.py -> IndependentMarginals",
    },
    {
        "name": "M1 — Weighted bootstrap (the fidelity ceiling)",
        "purpose": "Establish the best score any method could achieve, as a reference line.",
        "formula": (
            "Draw a real household i with probability   WGTP(i) / SUM of all WGTP,\n"
            "then copy its attributes verbatim."
        ),
        "symbols": "WGTP(i) = the ACS weight of real household i",
        "reading": (
            "Wins almost every metric, and that is expected rather than a discovery: it reproduces "
            "the real joint distribution because it copies real rows.\n\n"
            "It is reported as a CEILING, not a candidate. It can only ever emit combinations that "
            "already appear in the data, so it cannot generalise, and its residual error is pure "
            "sampling noise. The deployable choice is the best genuinely generative model."
        ),
        "example": "Association error 0.0209 — the practical floor for this dataset and sample size.",
        "code": "lib/models.py -> WeightedBootstrap",
    },
    {
        "name": "M2 — Chow-Liu tree Bayesian network",
        "purpose": "Keep the strongest dependencies while staying cheap to fit.",
        "formula": (
            "1. Weighted mutual information for every attribute pair:\n\n"
            "       I(A;B)  =  SUM over a,b of  p(a,b) x log(  p(a,b) / ( p(a) x p(b) )  )\n\n"
            "2. Build the maximum spanning tree over attributes, using I as edge weight.\n"
            "3. Factorise along that tree:\n\n"
            "       P(x)  =  P(root)  x  PRODUCT over edges (parent -> child) of  P(child | parent)"
        ),
        "symbols": (
            "I(A;B) = mutual information, how much knowing A tells you about B\n"
            "Each attribute has exactly one parent, except the root"
        ),
        "reading": (
            "A middle ground between full independence and the full joint. It captures the single "
            "strongest relationship for each attribute but nothing beyond a tree, so associations "
            "that depend on two or more other attributes at once are lost.\n\n"
            "Clearly beats independence (0.4831 vs 1.2047) but is well short of the winner."
        ),
        "example": "Association error 0.4831 — roughly 60% better than the baseline, 5x worse than M4.",
        "code": "lib/models.py -> ChowLiuTree",
    },
    {
        "name": "M3 — Gaussian copula",
        "purpose": "Model dependence through a correlated latent normal layer.",
        "formula": (
            "1. Map each category to an interval of [0,1] sized by its weighted probability.\n"
            "2. Draw a uniform value inside that interval and convert to a normal score:\n\n"
            "       z  =  PHI^-1( u )        where PHI^-1 is the inverse normal CDF\n\n"
            "3. Fit the weighted correlation matrix of the resulting z values.\n"
            "4. To generate: draw z ~ MultivariateNormal(0, R), convert back with u = PHI(z),\n"
            "   and read off whichever category's interval contains u."
        ),
        "symbols": (
            "PHI   = standard normal CDF\n"
            "R     = fitted correlation matrix, nudged onto the positive semi-definite cone so the "
            "Cholesky factor exists"
        ),
        "reading": (
            "Performed worst of the three generative models here (0.8372), and the reason is "
            "structural rather than a tuning failure. A copula captures MONOTONE association, which "
            "requires the categories to have a meaningful order.\n\n"
            "That holds for age and income, but home_type and work_mode are nominal — there is no "
            "sense in which 'detached' is greater than 'multifamily' — so ordering them is "
            "arbitrary and much of the real association cannot be expressed."
        ),
        "example": "Association error 0.8372, better than independence but worse than the tree model.",
        "code": "lib/models.py -> GaussianCopula",
    },
    {
        "name": "M4 — Latent class model  (SELECTED)",
        "purpose": "Reproduce joint structure by mixing several internally-simple subpopulations.",
        "formula": (
            "P(x)  =  SUM over classes c of   pi(c)  x  PRODUCT over attributes j of  P( x_j | c )\n\n"
            "Attributes are independent WITHIN a class; mixing the classes creates the correlation.\n"
            "Fitted by Expectation-Maximisation, weighted by WGTP:\n\n"
            "  E step:  r(i,c)  =  pi(c) x PRODUCT_j P( x_ij | c )   /   SUM over c' of the same\n\n"
            "  M step:  pi(c)        =  SUM_i WGTP(i) x r(i,c)  /  SUM_i WGTP(i)\n"
            "           P(x_j = v|c) =  SUM over i where x_ij = v of WGTP(i) x r(i,c)\n"
            "                           / SUM_i WGTP(i) x r(i,c)\n\n"
            "Iterate until the weighted log-likelihood stops improving."
        ),
        "symbols": (
            "c       = latent class index; 8 classes were used\n"
            "pi(c)   = share of the population in class c\n"
            "r(i,c)  = responsibility — the probability household i belongs to class c\n"
            "WGTP(i) = the ACS weight, so EM fits the population rather than the sample"
        ),
        "reading": (
            "The winner, and the classical model for exactly this kind of categorical survey data. "
            "Each latent class behaves like a coherent household type, and a household's attributes "
            "become correlated because they are generated together from one class.\n\n"
            "Nearly matches the bootstrap ceiling while remaining genuinely generative — it can "
            "produce plausible combinations that never appear verbatim in the sample.\n\n"
            "Trade-off: by far the slowest to fit (~40s), so it should be fitted once and cached "
            "rather than refitted per request."
        ),
        "example": (
            "Association error 0.0897 against the ceiling's 0.0209 and the baseline's 1.2047 — "
            "92.6% better than what the app does today."
        ),
        "code": "lib/models.py -> LatentClass",
    },
    {
        "name": "Donor (hot-deck) attachment of continuous detail",
        "purpose": "Give each generated persona real income, age, and cost-burden figures.",
        "formula": (
            "The models generate the six CATEGORICAL attributes only. For each generated bundle b:\n\n"
            "    choose a real household  i  among those whose bundle equals b,\n"
            "    with probability   WGTP(i) / SUM of WGTP over that same bundle,\n\n"
            "then copy its exact income, age, household size, cost burden, and PUMA."
        ),
        "symbols": "b = the generated combination of the six categorical attributes",
        "reading": (
            "Standard hot-deck imputation. It means every specific number shown in this workbook "
            "belongs to an actual Census record rather than being invented or interpolated.\n\n"
            "The division of labour is deliberate: the model decides WHICH kinds of household "
            "appear and how often, and the donor supplies realistic within-type detail."
        ),
        "example": (
            "Dolores Perez's $21,409 income, age 73, and 32% cost burden all come from one real "
            "Riverside County household matching her attribute bundle."
        ),
        "code": "04_select_personas.py -> attach_donor_detail()",
    },
    {
        "name": "Likely-response scoring function",
        "purpose": "Label each persona accept / unsure / reject from Census fields alone.",
        "formula": (
            "score  =  SUM of the weight of every rule that fires\n\n"
            "  AFFORDABILITY\n"
            "    -4.0   $23,000 exceeds 40% of annual household income\n"
            "    -2.5   $23,000 is 20-40% of annual household income\n"
            "    -1.0   $23,000 is 10-20% of annual household income\n"
            "    +1.5   $23,000 is under 10% of annual household income\n\n"
            "  EXISTING BURDEN  (ACS OCPIP)\n"
            "    -2.0   owner costs already exceed 30% of income\n"
            "    -1.5   owner costs exceed 50% of income  (stacks with the rule above)\n\n"
            "  CAPACITY\n"
            "    +2.0   high income bucket ($150k+)\n"
            "    +1.0   upper-middle income bucket ($75k-$150k)\n\n"
            "  USE CASE\n"
            "    +2.0   works from home, so a detached office has a concrete daily use\n"
            "    +1.5   household of 3 or more, so separated space relieves real pressure\n"
            "    -1.5   single-person household aged 65+, where the use case is weakest\n"
            "    +1.0   householder aged 35-54, the peak home-improvement life stage\n\n"
            "  LABEL\n"
            "    accept   if score >= +2.0\n"
            "    reject   if score <= -1.0\n"
            "    unsure   otherwise\n\n"
            "  HARD GUARDS, applied after the score\n"
            "    1. A household with zero or negative income is NOT SCORABLE and is removed from\n"
            "       the pool. Without this the price rules never fire and the persona drifts into\n"
            "       'accept' by default.\n"
            "    2. If the price exceeds 30% of income, the best available label is 'unsure'\n"
            "       unless the household is high-income. No lifestyle upside outweighs a third of\n"
            "       gross annual income."
        ),
        "symbols": "Every input is an ACS field or a value derived from one. No LLM judgement is involved.",
        "reading": (
            "Deliberately a transparent additive rule so that every label in this workbook can be "
            "audited and reproduced from the Census columns shown beside it.\n\n"
            "Among eligible households the rule yields 41.8% accept, 20.6% unsure, 37.6% reject. "
            "The 3 rejectors in this set are 20% of 15 — slightly BELOW the natural rate, so the "
            "persona set is not distorted by having asked for them."
        ),
        "example": (
            "Dolores Perez (NEO_15), income $21,409, cost burden 32%:\n"
            "    price is 107.4% of income   ->  -4.0\n"
            "    owner costs exceed 30%      ->  -2.0\n"
            "    total                           -6.0   ->  REJECT\n\n"
            "David Chen (NEO_01), income $518,691, remote worker, household of 5:\n"
            "    price is 4.4% of income     ->  +1.5\n"
            "    high income bucket          ->  +2.0\n"
            "    works from home             ->  +2.0\n"
            "    household of 3 or more      ->  +1.5\n"
            "    total                           +7.0   ->  ACCEPT"
        ),
        "code": "lib/rejection.py -> score_row()",
    },
    {
        "name": "Composite rank",
        "purpose": "Order the model comparison table.",
        "formula": (
            "For each of the five fidelity metrics, rank the models from best (1) to worst (5).\n\n"
            "    composite_rank  =  mean of those five ranks"
        ),
        "symbols": "The five metrics: marginal TVD, association error, purchase-triple TVD, full joint TVD, C2ST gap.",
        "reading": (
            "Used only for ordering the table, never for the decision itself.\n\n"
            "The actual selection rule was to take the best genuinely GENERATIVE model, which "
            "excludes the weighted bootstrap even though it ranks first — it copies real households "
            "and so serves as a ceiling rather than a candidate."
        ),
        "example": "M1 scored 1.4 and M4 scored 1.8; M4 was selected because M1 is the ceiling.",
        "code": "03_compare_models.py",
    },
]

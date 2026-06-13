// Bayesian Dixon-Coles with a hierarchical confederation-offset prior.
//
// Phase A (docs/bayesian-confederation-plan.md): the time dimension still
// enters through the per-match weights `w` — the same exponential time-decay /
// friendly weights the MLE model (wcpred/model.py) fits on. Dynamic
// random-walk team strengths are Phase B.
//
// The structural fix for weak cross-confederation anchoring: each team's
// attack and defence carry an additive confederation-level offset
// (atk_conf / dfn_conf). Intra-confederation matches only inform the
// team-level deviations — the shared offset cancels in the comparison — so the
// offsets themselves are pinned almost entirely by the rarer
// inter-confederation "bridge" matches, and shrink toward 0 (no bloc drift)
// when bridges carry no information (sigma_conf small).

functions {
  // Dixon-Coles low-score correction tau(x, y; lam, mu, rho), matching
  // model.DixonColes._tau: a multiplicative adjustment on the
  // independent-Poisson probability of the four low-scoring scorelines.
  real dc_tau(int x, int y, real lam, real mu, real rho) {
    if (x == 0 && y == 0) return 1 - lam * mu * rho;
    if (x == 0 && y == 1) return 1 + lam * rho;
    if (x == 1 && y == 0) return 1 + mu * rho;
    if (x == 1 && y == 1) return 1 - rho;
    return 1.0;
  }
}

data {
  int<lower=1> N;                          // matches
  int<lower=1> T;                          // teams
  int<lower=0> C;                          // confederations with an offset
  array[N] int<lower=1, upper=T> hi;       // home team index
  array[N] int<lower=1, upper=T> ai;       // away team index
  array[N] int<lower=0> hg;                // home goals
  array[N] int<lower=0> ag;                // away goals
  vector<lower=0>[N] w;                     // per-match weight (time decay etc.)
  vector<lower=0, upper=1>[N] hadv;         // 1 if the home side plays at home
  array[T] int<lower=0, upper=C> conf;     // team confederation (0 = unknown)
}

transformed data {
  vector[N] hg_v = to_vector(hg);
  vector[N] ag_v = to_vector(ag);
  vector[N] lg_hg;                          // lgamma(hg+1): Poisson normaliser
  vector[N] lg_ag;
  for (n in 1:N) {
    lg_hg[n] = lgamma(hg[n] + 1);
    lg_ag[n] = lgamma(ag[n] + 1);
  }
}

parameters {
  vector[T] atk_raw;                        // non-centred team deviations
  vector[T] dfn_raw;
  vector[C] atk_conf;                       // confederation attack offsets
  vector[C] dfn_conf;                       // confederation defence offsets
  real home;                                // home advantage (log-rate)
  real<lower=-0.2, upper=0.2> rho;          // DC correction (MLE grid range)
  real<lower=1e-3> sigma_atk;               // team-level spread (floored off 0)
  real<lower=1e-3> sigma_dfn;
  real<lower=1e-3> sigma_conf;              // between-confederation scale (key knob)
  real<lower=2, upper=80> nu;               // Student-t dof (bounded: 80 ≈ normal)
}

transformed parameters {
  vector[T] atk;
  vector[T] dfn;
  for (t in 1:T) {
    real oa = conf[t] > 0 ? atk_conf[conf[t]] : 0;
    real od = conf[t] > 0 ? dfn_conf[conf[t]] : 0;
    atk[t] = oa + sigma_atk * atk_raw[t];
    dfn[t] = od + sigma_dfn * dfn_raw[t];
  }
}

model {
  // --- priors ---
  // Student-t deviations keep legitimate outliers (Argentina, Spain) from
  // being squashed toward their confederation mean — the failure mode that
  // sank the rejected 2a design (docs/model-robustness-plan.md).
  atk_raw ~ student_t(nu, 0, 1);
  dfn_raw ~ student_t(nu, 0, 1);
  atk_conf ~ normal(0, sigma_conf);
  dfn_conf ~ normal(0, sigma_conf);
  sigma_atk ~ normal(0, 1);                 // half-normal (lower=0)
  sigma_dfn ~ normal(0, 1);
  sigma_conf ~ normal(0, 0.5);              // half-normal: offsets shrink w/o bridges
  nu ~ gamma(2, 0.1);
  home ~ normal(0, 0.5);
  rho ~ normal(0, 0.1);

  // --- gauge fixes ---
  // atk/dfn share a global shift degeneracy (atk_i += c, dfn_i -= c leaves
  // every rate unchanged); the confederation offsets a per-bloc one. Pin the
  // means — mirroring the MLE's atk.mean()=0 penalty. Predictions depend only
  // on atk_h+dfn_a and atk_a+dfn_h, which are invariant to these shifts.
  sum(atk) ~ normal(0, 0.01 * T);
  if (C > 0) {
    sum(atk_conf) ~ normal(0, 0.01 * C);
    sum(dfn_conf) ~ normal(0, 0.01 * C);
  }

  // --- weighted Dixon-Coles likelihood ---
  // log_lam/log_mu vectorised; the four-cell tau correction added per match.
  // Each match's whole log-likelihood is scaled by w[n] (power likelihood),
  // exactly as model.DixonColes weights its Poisson terms.
  {
    vector[N] log_lam = atk[hi] + dfn[ai] + home * hadv;
    vector[N] log_mu  = atk[ai] + dfn[hi];
    vector[N] lam = exp(log_lam);
    vector[N] mu  = exp(log_mu);
    vector[N] log_tau;
    for (n in 1:N)
      log_tau[n] = log(fmax(dc_tau(hg[n], ag[n], lam[n], mu[n], rho), 1e-9));
    target += sum(w .* (hg_v .* log_lam - lam - lg_hg
                        + ag_v .* log_mu - mu - lg_ag
                        + log_tau));
  }
}

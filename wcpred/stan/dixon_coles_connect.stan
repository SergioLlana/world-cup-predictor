// Bayesian Dixon-Coles with a CONNECTIVITY-WEIGHTED confederation-offset prior.
//
// Phase C (docs/bayesian-confederation-plan.md), formulation A. Identical to the
// static stan/dixon_coles.stan except that each team's confederation offset is
// scaled by a per-team weight conf_w in [0, 1] (its bridge-match share, mapped
// through config.BAYES_CONNECT_REF):
//
//     atk[t] = conf_w[t] * atk_conf[conf[t]] + sigma_atk * atk_raw[t]
//     dfn[t] = conf_w[t] * dfn_conf[conf[t]] + sigma_dfn * dfn_raw[t]
//
// Rationale: the uniform offset of dixon_coles.stan is pinned almost entirely by
// the bloc ELITE's inter-confederation "bridge" matches (only Japan/Australia/
// Korea play outside the AFC) yet applied equally to the isolated minnows that
// never anchor — inflating them, which in turn lets the elite harvest cheap
// credit beating them (the Australia-over-USA mechanism, known-limitations.md).
// Scaling the offset by connectivity lets a well-bridged team keep the offset it
// helped estimate (conf_w -> 1) while an isolated team is pulled toward the
// global scale (conf_w -> 0, no inherited bloc level). With conf_w = 1 for every
// team this reduces EXACTLY to dixon_coles.stan.
//
// NOTE: this breaks the exact cancellation of the offset in intra-confederation
// matches (two same-bloc teams with different conf_w no longer cancel it), so
// such games now weakly inform the offset. That is intended; --bridge-audit
// watches for any drift it introduces.

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
  real<lower=0> sigma_conf_scale;           // half-normal prior scale on sigma_conf
  vector[C] mu_atk_conf;                    // informative prior MEAN per bloc offset
  vector[C] mu_dfn_conf;                    // (all 0 = today's zero-mean model)
  vector<lower=0, upper=1>[T] conf_w;       // per-team offset weight (bridge share;
                                            // 1 = full offset = dixon_coles.stan)
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
    // Connectivity-weighted offset: a well-bridged team (conf_w -> 1) keeps the
    // full bloc offset; an isolated team (conf_w -> 0) is anchored to the global
    // scale. conf_w = 1 reduces this to the unweighted dixon_coles.stan.
    real oa = conf[t] > 0 ? conf_w[t] * atk_conf[conf[t]] : 0;
    real od = conf[t] > 0 ? conf_w[t] * dfn_conf[conf[t]] : 0;
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
  atk_conf ~ normal(mu_atk_conf, sigma_conf);
  dfn_conf ~ normal(mu_dfn_conf, sigma_conf);
  sigma_atk ~ normal(0, 1);                 // half-normal (lower=0)
  sigma_dfn ~ normal(0, 1);
  sigma_conf ~ normal(0, sigma_conf_scale); // half-normal: offsets shrink w/o bridges
                                            // (scale from data; <0.5 pins them toward 0)
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

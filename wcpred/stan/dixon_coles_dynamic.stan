// Bayesian Dixon-Coles with a hierarchical confederation-offset prior AND
// dynamic (random-walk) team strengths (docs/bayesian-engine.md).
//
// Difference from the static stan/dixon_coles.stan: time no longer enters
// through the exponential time-decay weights `w`. Instead each team's
// attack/defence *deviation* evolves as a Gaussian random walk over B discrete
// time blocks (e.g. half-years), and predictions use the most recent block's
// state. The confederation offset (atk_conf/dfn_conf) is unchanged — it is a
// per-bloc level the time-varying team deviations sit on top of, still pinned
// almost entirely by the rare inter-confederation "bridge" matches, so
// intra-bloc games cannot shift a whole confederation.
//
// Parameterisation is non-centred throughout (innovations ~ std-normal scaled
// by sigma) for sampling efficiency; the block-1 deviation keeps the
// Student-t robustness so legitimate outliers (Argentina) are not squashed.

functions {
  // Dixon-Coles low-score correction tau(x, y; lam, mu, rho), matching
  // model.DixonColes._tau — identical to the static model.
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
  int<lower=1> B;                          // time blocks (e.g. half-years)
  array[N] int<lower=1, upper=T> hi;       // home team index
  array[N] int<lower=1, upper=T> ai;       // away team index
  array[N] int<lower=0> hg;                // home goals
  array[N] int<lower=0> ag;                // away goals
  array[N] int<lower=1, upper=B> tb;       // time block of each match
  vector<lower=0>[N] w;                    // per-match weight (friendly/cross-conf)
  vector<lower=0, upper=1>[N] hadv;        // 1 if the home side plays at home
  array[T] int<lower=0, upper=C> conf;     // team confederation (0 = unknown)
  real<lower=0> sigma_conf_scale;          // half-normal prior scale on sigma_conf
  vector[C] mu_atk_conf;                   // informative prior MEAN per bloc offset
  vector[C] mu_dfn_conf;                   // (all 0 = today's zero-mean model)
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
  matrix[T, B] atk_z;                      // non-centred RW innovations (attack)
  matrix[T, B] dfn_z;                      // ... (defence)
  vector[C] atk_conf;                      // confederation attack offsets
  vector[C] dfn_conf;                      // confederation defence offsets
  real home;                               // home advantage (log-rate)
  real<lower=-0.2, upper=0.2> rho;         // DC correction (MLE grid range)
  // Scales feeding the cumulative random walk carry a loose upper bound: with
  // the non-centred parameterisation an unbounded scale can blow up during
  // warmup and make the cumulative sum overflow to inf+(-inf)=nan in the gauge
  // below. The bounds sit far above any plausible posterior (a half-year
  // strength step > 2 log-goals is absurd), so they do not shape the result.
  real<lower=1e-3, upper=5> sigma_atk;     // block-1 team spread (floored off 0)
  real<lower=1e-3, upper=5> sigma_dfn;
  real<lower=1e-3, upper=2> sigma_rw_atk;  // random-walk step scale (attack)
  real<lower=1e-3, upper=2> sigma_rw_dfn;  // ... (defence)
  real<lower=1e-3> sigma_conf;             // between-confederation scale (key parameter)
  real<lower=2, upper=80> nu;              // Student-t dof (bounded: 80 ≈ normal)
}

transformed parameters {
  matrix[T, B] atk;
  matrix[T, B] dfn;
  matrix[T, B] u_atk;                       // team deviation (offset removed)
  matrix[T, B] u_dfn;
  // Cumulative random walk per team: block 1 = sigma * z (initial deviation),
  // block b = block b-1 + sigma_rw * z (innovation).
  u_atk[, 1] = sigma_atk * atk_z[, 1];
  u_dfn[, 1] = sigma_dfn * dfn_z[, 1];
  for (b in 2:B) {
    u_atk[, b] = u_atk[, b - 1] + sigma_rw_atk * atk_z[, b];
    u_dfn[, b] = u_dfn[, b - 1] + sigma_rw_dfn * dfn_z[, b];
  }
  for (t in 1:T) {
    real oa = conf[t] > 0 ? atk_conf[conf[t]] : 0;
    real od = conf[t] > 0 ? dfn_conf[conf[t]] : 0;
    atk[t] = oa + u_atk[t];
    dfn[t] = od + u_dfn[t];
  }
}

model {
  // --- priors ---
  // Block-1 deviations are Student-t (robustness: keep Argentina/Spain
  // from being squashed toward their confederation mean); subsequent
  // random-walk innovations are standard normal.
  atk_z[, 1] ~ student_t(nu, 0, 1);
  dfn_z[, 1] ~ student_t(nu, 0, 1);
  if (B > 1) {
    to_vector(atk_z[, 2:B]) ~ std_normal();
    to_vector(dfn_z[, 2:B]) ~ std_normal();
  }
  atk_conf ~ normal(mu_atk_conf, sigma_conf);
  dfn_conf ~ normal(mu_dfn_conf, sigma_conf);
  sigma_atk ~ normal(0, 1);                 // half-normal (lower=0)
  sigma_dfn ~ normal(0, 1);
  sigma_rw_atk ~ normal(0, 0.2);            // half-normal: smooth evolution by default
  sigma_rw_dfn ~ normal(0, 0.2);
  sigma_conf ~ normal(0, sigma_conf_scale); // half-normal: offsets shrink w/o bridges
                                            // (scale from data; <0.5 pins them toward 0)
  nu ~ gamma(2, 0.1);
  home ~ normal(0, 0.5);
  rho ~ normal(0, 0.1);

  // --- gauge fixes ---
  // The atk/dfn global shift degeneracy (atk_i += c, dfn_i -= c leaves every
  // rate unchanged) is per time block here, so pin the team-deviation mean to 0
  // in every block; the confederation offsets carry the per-bloc one. Both pins
  // mirror the MLE's atk.mean()=0 penalty. Predictions depend only on
  // atk_h+dfn_a and atk_a+dfn_h, invariant to these shifts.
  for (b in 1:B) {
    sum(u_atk[, b]) ~ normal(0, 0.01 * T);
    sum(u_dfn[, b]) ~ normal(0, 0.01 * T);
  }
  if (C > 0) {
    sum(atk_conf) ~ normal(0, 0.01 * C);
    sum(dfn_conf) ~ normal(0, 0.01 * C);
  }

  // --- weighted Dixon-Coles likelihood (strengths indexed by match block) ---
  {
    vector[N] log_lam;
    vector[N] log_mu;
    for (n in 1:N) {
      log_lam[n] = atk[hi[n], tb[n]] + dfn[ai[n], tb[n]] + home * hadv[n];
      log_mu[n]  = atk[ai[n], tb[n]] + dfn[hi[n], tb[n]];
    }
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

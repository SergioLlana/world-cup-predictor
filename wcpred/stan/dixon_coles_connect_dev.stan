// Bayesian Dixon-Coles with CONNECTIVITY-WEIGHTED DEVIATION shrinkage.
//
// Connectivity-shrinkage experiment (rejected, docs/connectivity.md), deviation
// formulation. Identical to the
// static stan/dixon_coles.stan except that each team's own deviation from its
// confederation level is scaled by a per-team weight conf_w in [0, 1] (its
// bridge-match share, mapped through config.BAYES_CONNECT_REF):
//
//     atk[t] = atk_conf[conf[t]] + sigma_atk * conf_w[t] * atk_raw[t]
//     dfn[t] = dfn_conf[conf[t]] + sigma_dfn * conf_w[t] * dfn_raw[t]
//
// This is the classic hierarchical "partial pooling" reading of the idea: a
// well-bridged team (conf_w -> 1) is free to deviate from its bloc; a poorly
// bridged team (conf_w -> 0) is pulled toward its CONFEDERATION mean (not the
// global 0 of formulation A). It keeps the bloc offset intact — only the
// team-level spread is connectivity-gated. With conf_w = 1 for every team this
// reduces EXACTLY to dixon_coles.stan.
//
// Contrast with formulation A (dixon_coles_connect.stan), which scaled the
// OFFSET and shrank toward the global scale; A was rejected because a weak
// bloc's offset is negative, so attenuating it toward 0 RAISES that bloc.

functions {
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
  vector<lower=0, upper=1>[T] conf_w;       // per-team deviation weight (bridge share;
                                            // 1 = full deviation = dixon_coles.stan)
}

transformed data {
  vector[N] hg_v = to_vector(hg);
  vector[N] ag_v = to_vector(ag);
  vector[N] lg_hg;
  vector[N] lg_ag;
  for (n in 1:N) {
    lg_hg[n] = lgamma(hg[n] + 1);
    lg_ag[n] = lgamma(ag[n] + 1);
  }
}

parameters {
  vector[T] atk_raw;
  vector[T] dfn_raw;
  vector[C] atk_conf;
  vector[C] dfn_conf;
  real home;
  real<lower=-0.2, upper=0.2> rho;
  real<lower=1e-3> sigma_atk;
  real<lower=1e-3> sigma_dfn;
  real<lower=1e-3> sigma_conf;
  real<lower=2, upper=80> nu;
}

transformed parameters {
  vector[T] atk;
  vector[T] dfn;
  for (t in 1:T) {
    real oa = conf[t] > 0 ? atk_conf[conf[t]] : 0;
    real od = conf[t] > 0 ? dfn_conf[conf[t]] : 0;
    // Connectivity-weighted deviation: a well-bridged team (conf_w -> 1) keeps
    // its full deviation; an isolated team (conf_w -> 0) is pulled toward its
    // confederation level. conf_w = 1 reduces this to dixon_coles.stan.
    atk[t] = oa + sigma_atk * conf_w[t] * atk_raw[t];
    dfn[t] = od + sigma_dfn * conf_w[t] * dfn_raw[t];
  }
}

model {
  atk_raw ~ student_t(nu, 0, 1);
  dfn_raw ~ student_t(nu, 0, 1);
  atk_conf ~ normal(mu_atk_conf, sigma_conf);
  dfn_conf ~ normal(mu_dfn_conf, sigma_conf);
  sigma_atk ~ normal(0, 1);
  sigma_dfn ~ normal(0, 1);
  sigma_conf ~ normal(0, sigma_conf_scale);
  nu ~ gamma(2, 0.1);
  home ~ normal(0, 0.5);
  rho ~ normal(0, 0.1);

  sum(atk) ~ normal(0, 0.01 * T);
  if (C > 0) {
    sum(atk_conf) ~ normal(0, 0.01 * C);
    sum(dfn_conf) ~ normal(0, 0.01 * C);
  }

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

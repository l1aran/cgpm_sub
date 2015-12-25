# -*- coding: utf-8 -*-

#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import numpy as np
from math import isnan

import gpmcc.utils.general as gu
import gpmcc.utils.config as cu

class Dim(object):
    """Holds data, model type, clusters, and shared hyperparameters of
    component GPMs. Exposes the cluster of each row for model dependent
    composition."""

    def __init__(self, X, dist, index, distargs=None, Zr=None, n_grid=30,
            hypers=None, mode='collapsed'):
        """Dimension constructor. Assignment of rows to clusters (Zr) is
        not maintained internally. The dataset X is also summarized by the
        sufficient statistics and is not stored.

        Arguments:
        ... X (np.array) : Array of data. Must be compatible with `dist`.
        Missing entries must be np.nan.
        ... dist (str) : DistributionGpm name see `gpmcc.utils.config`.
        ... index (int) : Identifier for this dim.

        Keyword Arguments:
        ... Zr (list) L Partition of data into clusters, where Zr[i] is the
        cluster index of row i. If None, is intialized from CRP(alpha=1).
        ... n_grid (int) : Number of bins in the hyperparameter grid.
        """
        # Identifier.
        self.index = index

        # Number of observations.
        self.N = len(X)

        # Model type.
        self.model = cu.distgpm_class(dist)
        self.cctype = self.model.name()
        self.distargs = distargs if distargs is not None else {}

        # Hyperparams.
        self.hyper_grids = self.model.construct_hyper_grids(
            X[~np.isnan(X)], n_grid)
        self.hypers = hypers
        if hypers is None:
            self.hypers = dict()
            # Randomly initialize each hyper h by sampling from grid.
            for h in self.hyper_grids:
                self.hypers[h] = np.random.choice(self.hyper_grids[h])
        assert self.hypers.keys() == self.hyper_grids.keys()

        # Row partitioning.
        if Zr is None:
            Zr, _, _ = gu.crp_gen(len(X), 1)
        self.reassign(X, Zr)

        # Auxiliary singleton model.
        self.aux_model = None

    def incorporate(self, x, k):
        """Record an observation x in clusters[k]."""
        self.N += 1
        if isnan(x):
            return
        self.clusters[k].incorporate(x)

    def unincorporate(self, x, k):
        """Remove observation x from clusters[k]."""
        self.N -= 1
        if isnan(x):
            return
        self.clusters[k].unincorporate(x)

    def predictive_logp(self, x, k):
        """Returns the predictive logp of x in clusters[k]. If x has been
        assigned to clusters[k], then use the unincorporate/incorporate
        interface to compute the true predictive logp."""
        if isnan(x):
            return 0
        return self.clusters[k].predictive_logp(x)

    def singleton_logp(self, x):
        """Returns the predictive log_p of X[rowid] in a new cluster."""
        if isnan(x):
            return 0
        self.aux_model = self.model(distargs=self.distargs, **self.hypers)
        lp = self.aux_model.singleton_logp(x)
        return lp

    def move_to_cluster(self, x, move_from, move_to):
        """Move x from clusters[move_from] to clusters[move_to]."""
        if isnan(x):
            return
        self.clusters[move_from].unincorporate(x)
        self.clusters[move_to].incorporate(x)

    def destroy_singleton_cluster(self, x, to_destroy, move_to):
        """Move x from clusters[move_to], destroy clusters[to_destroy]."""
        if isnan(x):
            return
        self.clusters[move_to].incorporate(x)
        del self.clusters[to_destroy]

    def create_singleton_cluster(self, x, current):
        """Remove x from clusters[current] and create a new singleton
        cluster.
        """
        self.clusters.append(self.aux_model)
        if isnan(x):
            return
        self.clusters[current].unincorporate(x)
        self.clusters[-1].incorporate(x)

    def marginal_logp(self, k=None):
        """If k is not None, teturns the marginal log_p of clusters[k].
        Otherwise returns the sum of marginal log_p over all clusters."""
        if k is not None:
            return self.clusters[k].marginal_logp()
        return sum(cluster.marginal_logp() for cluster in self.clusters)

    def transition_hypers(self):
        """Updates the hyperparameters and the component parameters."""
        # Transition component parameters.
        for cluster in self.clusters:
            cluster.transition_params()
        # Transition hyperparameters.
        targets = self.hypers.keys()
        np.random.shuffle(targets)
        for target in targets:
            logps = self.calc_hyper_proposal_logps(target)
            proposal = gu.log_pflip(logps)
            self.hypers[target] = self.hyper_grids[target][proposal]
        # Update the clusters.
        for cluster in self.clusters:
            cluster.set_hypers(self.hypers)

    def calc_hyper_proposal_logps(self, target):
        """Computes the marginal likelihood (over all clusters) for each
        hyperparameter value in self.hyper_grids[target].
        p(h|X) \prop p(h)p(X|h)
        """
        logps = []
        hypers = self.hypers.copy()
        for g in self.hyper_grids[target]:
            hypers[target] = g
            logp = 0
            for cluster in self.clusters:
                cluster.set_hypers(hypers)
                logp += cluster.marginal_logp()
                cluster.set_hypers(self.hypers)
            logps.append(logp)
        return logps

    def reassign(self, X, Zr):
        """Reassigns data X to new clusters according to partitioning, Zr.
        Destroys and recreates clusters.
        """
        assert len(X) == len(Zr)
        self.clusters = []
        K = max(Zr) + 1

        for k in xrange(K):
            cluster = self.model(distargs=self.distargs, **self.hypers)
            self.clusters.append(cluster)

        for x, k in zip(X, Zr):
            if not isnan(x):
                self.clusters[k].incorporate(x)

        for cluster in self.clusters:
            cluster.transition_params()

    def get_suffstats(self):
        return [cluster.get_suffstats() for cluster in self.clusters]

    def is_collapsed(self):
        return self.model.is_collapsed()

    def plot_dist(self, X, Y=None, ax=None):
        """Plots the predictive distribution and histogram of X."""
        self.model.plot_dist(X[~np.isnan(X)], self.clusters,
            ax=ax, Y=Y, hist=False)

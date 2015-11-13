# -*- coding: utf-8 -*-

#   Copyright (c) 2010-2015, MIT Probabilistic Computing Project
#
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

import math
import numpy as np
import pylab

import gpmcc.utils.sampling as su
import gpmcc.utils.general as gu

def test_predictive_draw(state, N=None):
    if state.n_cols != 2:
        print("state must have exactly 2 columns")
        return

    if N is None:
        N = state.n_rows

    view_1 = state.Zv[0]
    view_2 = state.Zv[1]

    if view_1 != view_2:
        print("Columns not in same view")
        return

    log_crp = su.get_cluster_crps(state, 0)
    K = len(log_crp)

    X = np.zeros(N)
    Y = np.zeros(N)

    clusters_col_1 = su.create_cluster_set(state, 0)
    clusters_col_2 = su.create_cluster_set(state, 1)

    for i in range(N):
        c = gu.log_pflip(log_crp)
        x = clusters_col_1[c].predictive_draw()
        y = clusters_col_2[c].predictive_draw()

        X[i] = x
        Y[i] = y

    pylab.scatter(X,Y, color='red', label='inferred')
    pylab.scatter(state.dims[0].X, state.dims[1].X, color='blue', label='actual')
    pylab.show()

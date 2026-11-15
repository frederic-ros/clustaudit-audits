# name: Density peaks
# family: Density
# needs-k: yes
# requirements: numpy scipy
# reference: Rodriguez and Laio (2014), Science 344:1492; d_c = 2% quantile of pairwise distances, Gaussian kernel
import numpy as np
from scipy.spatial.distance import pdist, squareform


def cluster(X, seed, n_clusters=None, percent=2.0):
    X = np.asarray(X, float)
    n = len(X)
    D = squareform(pdist(X))
    dc = np.percentile(D[np.triu_indices(n, 1)], percent)
    rho = np.exp(-(D / dc) ** 2).sum(1) - 1.0          # local density
    order = np.argsort(-rho)
    delta = np.zeros(n)
    nn_up = np.full(n, -1)
    delta[order[0]] = D[order[0]].max()
    for i in range(1, n):                                # distance to the nearest denser point
        p, higher = order[i], order[:i]
        j = higher[np.argmin(D[p, higher])]
        delta[p], nn_up[p] = D[p, j], j
    centres = np.argsort(-rho * delta)[:n_clusters]      # the K largest gamma = rho * delta
    labels = np.full(n, -1)
    labels[centres] = np.arange(len(centres))
    for p in order:                                      # follow the nearest denser neighbour
        if labels[p] == -1 and nn_up[p] >= 0:
            labels[p] = labels[nn_up[p]]
    return labels

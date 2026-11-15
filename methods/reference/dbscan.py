# name: DBSCAN
# family: Density
# needs-k: no
# requirements: numpy scikit-learn
# reference: Ester et al. (1996); eps = 90th percentile of the 5-NN distance, min_samples = max(5, d)
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors


def cluster(X, seed, n_clusters=None):
    dist, _ = NearestNeighbors(n_neighbors=5).fit(X).kneighbors(X)
    eps = float(np.percentile(dist[:, -1], 90))
    return DBSCAN(eps=eps, min_samples=max(5, X.shape[1])).fit_predict(X)

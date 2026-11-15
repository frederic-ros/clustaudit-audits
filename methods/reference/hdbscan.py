# name: HDBSCAN
# family: Density
# needs-k: no
# requirements: scikit-learn
# reference: Campello et al. (2013); scikit-learn HDBSCAN, min_cluster_size 10, min_samples 5
from sklearn.cluster import HDBSCAN


def cluster(X, seed, n_clusters=None):
    return HDBSCAN(min_cluster_size=10, min_samples=5).fit_predict(X)

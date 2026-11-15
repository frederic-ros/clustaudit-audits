# name: OPTICS
# family: Density
# needs-k: no
# requirements: scikit-learn
# reference: Ankerst et al. (1999); scikit-learn OPTICS, min_samples 5, xi 0.05
from sklearn.cluster import OPTICS


def cluster(X, seed, n_clusters=None):
    return OPTICS(min_samples=5, xi=0.05).fit_predict(X)

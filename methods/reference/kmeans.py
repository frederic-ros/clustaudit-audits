# name: K-Means
# family: Centroid
# needs-k: yes
# requirements: scikit-learn
# reference: MacQueen (1967); scikit-learn KMeans, 10 initialisations
from sklearn.cluster import KMeans


def cluster(X, seed, n_clusters=None):
    return KMeans(n_clusters=n_clusters, n_init=10, random_state=seed).fit_predict(X)

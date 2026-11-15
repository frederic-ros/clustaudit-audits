# name: Spectral
# family: Graph
# needs-k: yes
# requirements: scikit-learn
# reference: spectral clustering on a k-nearest-neighbour graph (scikit-learn SpectralClustering)
from sklearn.cluster import SpectralClustering


def cluster(X, seed, n_clusters=None):
    return SpectralClustering(n_clusters=n_clusters, affinity="nearest_neighbors",
                              assign_labels="kmeans", random_state=seed).fit_predict(X)

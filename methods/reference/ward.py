# name: Ward
# family: Connectivity
# needs-k: yes
# requirements: scikit-learn
# reference: agglomerative clustering, Ward linkage
from sklearn.cluster import AgglomerativeClustering


def cluster(X, seed, n_clusters=None):
    return AgglomerativeClustering(n_clusters=n_clusters, linkage="ward").fit_predict(X)

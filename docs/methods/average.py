# name: Average linkage
# family: Connectivity
# needs-k: yes
# requirements: scikit-learn
# reference: agglomerative clustering, average linkage
from sklearn.cluster import AgglomerativeClustering


def cluster(X, seed, n_clusters=None):
    return AgglomerativeClustering(n_clusters=n_clusters, linkage="average").fit_predict(X)

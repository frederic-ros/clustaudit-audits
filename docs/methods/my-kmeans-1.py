# name: my-kmeans
# family: Centroid
# needs-k: yes
# requirements: numpy scikit-learn
def cluster(X, seed, n_clusters=None):
    """X: array (n, d). Return one integer label per row;
    -1 = point left unassigned. n_clusters is given when
    your method needs the number of clusters."""
    from sklearn.cluster import KMeans
    k = n_clusters or 5
    return KMeans(k, n_init=10, random_state=seed).fit_predict(X)

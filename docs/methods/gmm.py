# name: GMM
# family: Centroid
# needs-k: yes
# requirements: scikit-learn
# reference: Gaussian mixture, full covariances (scikit-learn GaussianMixture)
from sklearn.mixture import GaussianMixture


def cluster(X, seed, n_clusters=None):
    return GaussianMixture(n_components=n_clusters, random_state=seed).fit_predict(X)

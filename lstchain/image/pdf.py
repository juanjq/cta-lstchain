import numpy as np


def log_gaussian(x, mean, sigma):
    """
    Evaluate the log of a normal law

    Parameters
    ----------
    x: float or array-like
        Value at which the log gaussian is evaluated
    mean: float
        Central value of the normal distribution
    sigma: float
        Width of the normal distribution

    Returns
    -------
    log_pdf: float or array-like
        Log of the evaluation of the normal law at x
    """

    log_pdf = -(x - mean) ** 2 / (2 * sigma ** 2)
    log_pdf = log_pdf - np.log((np.sqrt(2 * np.pi) * sigma))

    return log_pdf


def log_gaussian2d(size, x, y, x_cm, y_cm, width, length, psi):
    """
    Evaluate the log of a bi-dimensional gaussian law

    Parameters
    ----------
    size: float
        Integral of the 2D Gaussian
    x, y: float or array-like
        Position at which the log gaussian is evaluated
    x_cm, y_cm: float
        Center of the 2D Gaussian
    width, length: float
        Standard deviations of the 2 dimensions of the 2D Gaussian law
    psi: float
        Orientation of the 2D Gaussian

    Returns
    -------
    log_pdf: float or array-like
        Log of the evaluation of the 2D gaussian law at (x,y)

    """
    scale_w = 1. / (2. * width ** 2)
    scale_l = 1. / (2. * length ** 2)
    a = np.cos(psi) ** 2 * scale_l + np.sin(psi) ** 2 * scale_w
    b = np.sin(2 * psi) * (scale_w - scale_l) / 2.
    c = np.cos(psi) ** 2 * scale_w + np.sin(psi) ** 2 * scale_l

    norm = 1. / (2 * np.pi * width * length)

    log_pdf = - (a * (x - x_cm) ** 2 - 2 * b * (x - x_cm) * (y - y_cm) + c * (
                y - y_cm) ** 2)

    log_pdf += np.log(norm) + np.log(size)

    return log_pdf


def logAsy_gaussian2d(size, x, y, x_cm, y_cm, width, length, psi ,rl):
    """
    Evaluate the log of a bi-dimensional gaussian law with asymmetry along the
    length

    Parameters
    ----------
    size: float
        Integral of the 2D Gaussian
    x, y: float or array-like
        Position at which the log gaussian is evaluated
    x_cm, y_cm: float
        Center of the 2D Gaussian
    width, length: float
        Standard deviations of the 2 dimensions of the 2D Gaussian law
    psi: float
        Orientation of the 2D Gaussian
    rl: float
        asymmetry factor between the two lengths

    Returns
    -------
    log_pdf: float or array-like
        Log of the evaluation of the 2D gaussian law at (x,y)

    """
    le = (x - x_cm) * np.cos(psi) + (y - y_cm) * np.sin(psi)
    wi = -(x - x_cm) * np.sin(psi) + (y - y_cm) * np.cos(psi)
    pos = (le < 0.0)
    rl_array = rl * pos + 1 * ~pos
    norm = 1/((rl + 1.0) * np.pi * width * length)
    a = 2 * (rl_array*length)**2
    b = 2 * width**2
    log_pdf = le**2/a + wi**2/b
    return np.log(norm) + np.log(size) - log_pdf

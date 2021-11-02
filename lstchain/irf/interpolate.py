import numpy as np
import logging
import astropy.units as u
from astropy.table import Table, QTable
from astropy.io import fits

from lstchain.irf.hdu_table import get_target_params
from lstchain.reco.utils import min_distance

from pyirf.io.gadf import (
    create_aeff2d_hdu,
    create_energy_dispersion_hdu  # ,create_psf_table_hdu
)
from pyirf.interpolation import (
    interpolate_effective_area_per_energy_and_fov,
    interpolate_energy_dispersion  # ,interpolate_psf_table
)
from scipy.spatial import Delaunay

log = logging.getLogger(__name__)


def interp_params(params_list, data):
    """
    From a given list of angular parameters, to be used for interpolation,
    take values from a given data table/dict.

    Returns the neccessary values with applied functions as need be for the
    interpolation, for each parameter as a list.
    """
    mc_pars = []
    if "ZEN_PNT" in params_list:
        mc_pars.append(
            np.cos(u.Quantity(data["ZEN_PNT"]).to_value(u.rad))
        )

    if "B_DELTA" in params_list:
        mc_pars.append(
            np.sin(
                u.Quantity(data["B_DELTA"]).to_value(u.rad)
            )
        )

    return mc_pars


def check_in_delaunay_triangle(irfs, data_params):
    """
    From a given list of IRFs as grid points used for interpolation, retrieve
    the Delaunay triangulation list of IRFs, where the simplex includes the
    target points in data_params.

    If the target point does not exist inside the simplex, the IRF
    corresponding to the nearest point in the simplex, closest to the
    target value.

    If the list of given IRFs are not enough for calculating the Delaunay
    triangulation, an empty list is returned.

    Parameters
    ------------
    irfs: List of IRFs to check for Delaunay triangulation.
        'List'
    data_pars: Dict of arrays of range of parameters of the observed data
        in the event list, to check for interpolation.
        'Dict'

    Returns
    ----------
    irf_list: Revised list of IRFs after the checks.
        'List'
    data_pars: Updated dict of target parameters for interpolation.
        'Dict'
    """
    # Exclude AZ_PNT as target interpolation parameter
    d = data_params.copy()
    d.pop("AZ_PNT", None)
    data_pars = [*d.keys()]

    new_irfs = []
    mc_params = np.empty((len(irfs), len(data_pars)))

    for i, irf in enumerate(irfs):
        f = fits.open(irf)[1].header

        mc_pars = interp_params(data_pars, f)
        mc_params[i, :] = np.array(mc_pars)

    data_val = np.array(interp_params(data_pars, data_params))

    try:
        tri = Delaunay(mc_params)
    except ValueError:
        log.error('Not enough grid values for Delaunay triangulation')
        return d, new_irfs

    # Find the nearest simplex with the target data values
    # by checking the maximum plane distance with all simplices
    dist_pt = tri.plane_distance(data_val)
    id_simp = np.where(dist_pt == dist_pt.max())
    nearest_simplex = tri.simplices[id_simp]
    nearest_pts = tri.points[nearest_simplex][0]

    # Check if the target values are inside or outside this simplex
    tri_near = Delaunay(nearest_pts)
    target_check = tri_near.find_simplex(data_val)

    if target_check == -1:
        log.error(
            "Target value is outside interpolation. Using the nearest grid"
            " point to the closest Delaunay simplex for interpolation."
        )
        # Get the nearest point to the new simplex, ie. projection to the
        # closest facet from the target point.
        proj = []
        dist = []
        for i in range(len(data_pars)+1):
            pt_1 = nearest_pts[i]
            pt_2 = nearest_pts[
                (i + 1) % (len(data_pars)+1)
            ]
            proj_pt, d = min_distance(pt_1, pt_2, data_val)
            proj.append(proj_pt)
            dist.append(d)

        proj = np.array(proj)
        data_val_new = proj[np.where(dist == np.min(dist))][0]

        # get the new data_params for interpolation
        data_params_new = get_target_params(
            zen=np.arccos(data_val_new[0]),
            b_delta=np.arcsin(data_val_new[1])
        )
    else:
        data_params_new = data_params

    for i in nearest_simplex[0]:
        new_irfs.append(irfs[i])

    return data_params_new, new_irfs


def compare_irfs(irfs):
    """
    Compare the given list of IRFs with various selection cuts, data binning
    and relevant metadata values.
    """
    bin_sim = False
    meta_sim = False

    params = []
    meta = []

    # For fixed gammaness/theta cuts
    select_meta = ["HDUCLAS3", "INSTRUME", "GH_CUT", "RAD_MAX", "G_OFFSET"]
    cols = Table.read(irfs[0], hdu="ENERGY DISPERSION").columns[:-1]

    for i, irf in enumerate(irfs):
        e_table = Table.read(irf, hdu="ENERGY DISPERSION")
        for j, col in enumerate(cols):
            params.append(e_table[col].quantity[0])
        for m in select_meta:
            if m in e_table.meta:
                meta.append(e_table.meta[m])

    # Comparing metadata
    meta_2, meta_ind = np.unique(meta, return_index=True)

    if len(meta_2) == int(len(meta)/len(irfs)):
        if (meta_2[np.argsort(meta_ind)] == meta[:int(len(meta)/len(irfs))]).all():
            meta_sim = True

    # Comparing other paramater axes in IRFs
    for i in np.arange(len(cols)):
        a = [params[len(cols)*j + i] for j in np.arange(len(irfs))]
        a2, a_ind = np.unique(a, return_index=True)
        if len(a2) == len(params[i]):
            if (a2[np.argsort(a_ind)] == params[i].value).all():
                bin_sim = True

    return bin_sim * meta_sim


def load_irf_grid(irfs, extname, interp_col):
    """
    From a given list of IRFs, load the list of IRF data values that can be
    interpolated (Effective Area and Energy Dispersion for now)

    Parameters
    ------------
    irfs: List of IRFs to use to interpolate
        List
    extname: Name of the IRF to be extracted
        Str
    interp_col: Name of the column whose values are to be interpolated
        Str

    Returns
    ----------
    irf_list: List of columns of the IRF from each file
        'numpy.stack'
    """
    irf_list = []
    for irf in irfs:
        irf_list.append(
            QTable.read(irf, hdu=extname)[interp_col][0].T
        )
    return np.stack(irf_list)


def interpolate_irf(irfs, data_pars, interp_method="linear"):
    """
    Using pyirf functions with a list of IRFs and parameters to compare with
    data, to interpolate over, to get the closest match

    For now only Effective Area and Energy Dispersion is interpolated over.

    Parameters
    ------------
    irfs: List of IRFs to use to interpolate
        List
    data_pars: Dict of arrays of range of parameters of the observed data
        in the event list, to check for interpolation.
        'Dict'
    interp_method: Method of interpolation to be used by
        scipy.interpolate.griddata. Values can be "linear", "nearest", "cubic"
        'Str'

    Returns
    ------------
    irf_interp: Final interpolated IRF
        'astropy.io.fits'
    """

    # Gather the parameters to use for interpolation

    # Exclude AZ_PNT as target interpolation parameter
    d = data_pars.copy()
    d.pop("AZ_PNT", None)
    params = [*d.keys()]
    n_grid = len(irfs)
    irf_pars = np.empty((n_grid, len(params)))
    interp_pars = list()

    extra_keys = [
        "TELESCOP", "INSTRUME", "FOVALIGN",
        "GH_CUT", "G_OFFSET", "RAD_MAX", "B_TOTAL", "B_INC"
        ]
    main_headers = fits.open(irfs[0])[1].header

    if main_headers["HDUCLAS3"] == "POINT-LIKE":
        point_like = True
    else:
        point_like = False

    # Update headers to be added to the final IRFs
    extra_headers = dict(
        (k, main_headers[k]) for k in extra_keys if k in main_headers
    )
    for par in data_pars.keys():
        extra_headers[par] = str(data_pars[par].to(u.deg))

    for i in np.arange(n_grid):
        f = fits.open(irfs[i])[1].header
        mc_pars = interp_params(params, f)
        irf_pars[i, :] = np.array(mc_pars)

    interp_pars = interp_params(params, data_pars)
    # Keep interp_pars as a tuple to keep the right dimensions in interpolation
    interp_pars = tuple(interp_pars)
    irf_interp = fits.HDUList([fits.PrimaryHDU(), ])

    # Read select IRFs into lists and extract the necessary columns
    hdus_interp = fits.open(irfs[0])

    try:
        hdus_interp["EFFECTIVE AREA"]
        effarea_list = load_irf_grid(
            irfs, extname="EFFECTIVE AREA", interp_col="EFFAREA"
        )

        temp_irf = QTable.read(irfs[0], hdu="EFFECTIVE AREA")
        e_true = np.append(temp_irf["ENERG_LO"][0], temp_irf["ENERG_HI"][0][-1])
        fov_off = np.append(temp_irf["THETA_LO"][0], temp_irf["THETA_HI"][0][-1])

        aeff_interp = interpolate_effective_area_per_energy_and_fov(
            effarea_list, irf_pars, interp_pars, method=interp_method
        )

        aeff_hdu_interp = create_aeff2d_hdu(
            aeff_interp.T,
            true_energy_bins=e_true,
            fov_offset_bins=fov_off,
            point_like=point_like,
            extname="EFFECTIVE AREA",
            **extra_headers,
        )

        irf_interp.append(aeff_hdu_interp)

    except KeyError:
        log.error("Effective Area not present for IRF interpolation")

    try:
        hdus_interp["ENERGY DISPERSION"]
        edisp_list = load_irf_grid(
            irfs, extname="ENERGY DISPERSION", interp_col="MATRIX"
        )
        temp_irf = QTable.read(irfs[0], hdu="ENERGY DISPERSION")

        # Check the units as well
        e_true = np.append(temp_irf["ENERG_LO"][0], temp_irf["ENERG_HI"][0][-1])
        e_migra = np.append(temp_irf["MIGRA_LO"][0], temp_irf["MIGRA_HI"][0][-1])
        fov_off = np.append(temp_irf["THETA_LO"][0], temp_irf["THETA_HI"][0][-1])

        edisp_interp = interpolate_energy_dispersion(
            edisp_list, irf_pars, interp_pars, method=interp_method
        )

        edisp_hdu_interp = create_energy_dispersion_hdu(
            edisp_interp,
            true_energy_bins=e_true,
            migration_bins=e_migra,
            fov_offset_bins=fov_off,
            point_like=point_like,
            extname="ENERGY DISPERSION",
            **extra_headers,
        )

        irf_interp.append(edisp_hdu_interp)

    except KeyError:
        log.error("Energy Dispersion not present for IRF interpolation")

    """
    if not point_like:
        try:
            hdus_interp["PSF"]
            psf_list = load_irf_grid(
                irfs, extname="PSF", interp_col="RPSF"
            )
            tem_irf = QTable.read(irfs[0], hdu="PSF")

            e_true = np.append(temp_irf["ENERG_LO"][0], temp_irf["ENERG_HI"][0][-1])
            src_bins = np.append(temp_irf["RAD_LO"][0], temp_irf["RAD_HI"][0][-1])
            fov_off = np.append(temp_irf["THETA_LO"][0], temp_irf["THETA_HI"][0][-1])

            psf_interp = interpolate_psf_table(
                psf_list, irf_pars,
                interp_pars, src_bins,
                cumulative=cumulative
                method=interp_method
            )
            psf_hdu_interp = create_psf_table_hdu(
                psf_interp,
                true_energy=e_true,
                source_offset_bins=src_bins,
                fov_offset_bins=fov_off,
                extname="PSF",
                **extra_headers
            )

            irf_interp.append(psf_hdu_interp)
        except KeyError:
            log.error("PSF HDU not present for IRF interpolation")
    """
    return irf_interp

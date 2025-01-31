# Licensed under a 3-clause BSD style license - see LICENSE.rst

import numpy as np

from astropy import units as u
from astropy.utils.misc import unbroadcast

from .wcs import WCS, WCSSUB_LONGITUDE, WCSSUB_LATITUDE, WCSSUB_CELESTIAL

__doctest_skip__ = ['wcs_to_celestial_frame', 'celestial_frame_to_wcs']

__all__ = ['add_stokes_axis_to_wcs', 'celestial_frame_to_wcs',
           'wcs_to_celestial_frame', 'proj_plane_pixel_scales',
           'proj_plane_pixel_area', 'is_proj_plane_distorted',
           'non_celestial_pixel_scales', 'skycoord_to_pixel',
           'pixel_to_skycoord', 'custom_wcs_to_frame_mappings',
           'custom_frame_to_wcs_mappings', 'pixel_to_pixel',
           'local_partial_pixel_derivatives']


def add_stokes_axis_to_wcs(wcs, add_before_ind):
    """
    Add a new Stokes axis that is uncorrelated with any other axes.

    Parameters
    ----------
    wcs : `~astropy.wcs.WCS`
        The WCS to add to
    add_before_ind : int
        Index of the WCS to insert the new Stokes axis in front of.
        To add at the end, do add_before_ind = wcs.wcs.naxis
        The beginning is at position 0.

    Returns
    -------
    A new `~astropy.wcs.WCS` instance with an additional axis
    """

    inds = [i + 1 for i in range(wcs.wcs.naxis)]
    inds.insert(add_before_ind, 0)
    newwcs = wcs.sub(inds)
    newwcs.wcs.ctype[add_before_ind] = 'STOKES'
    newwcs.wcs.cname[add_before_ind] = 'STOKES'
    return newwcs


def _wcs_to_celestial_frame_builtin(wcs):

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import FK4, FK4NoETerms, FK5, ICRS, ITRS, Galactic

    # Import astropy.time here otherwise setup.py fails before extensions are compiled
    from astropy.time import Time

    if wcs.wcs.lng == -1 or wcs.wcs.lat == -1:
        return None

    radesys = wcs.wcs.radesys

    if np.isnan(wcs.wcs.equinox):
        equinox = None
    else:
        equinox = wcs.wcs.equinox

    xcoord = wcs.wcs.ctype[wcs.wcs.lng][:4]
    ycoord = wcs.wcs.ctype[wcs.wcs.lat][:4]

    # Apply logic from FITS standard to determine the default radesys
    if radesys == '' and xcoord == 'RA--' and ycoord == 'DEC-':
        if equinox is None:
            radesys = "ICRS"
        elif equinox < 1984.:
            radesys = "FK4"
        else:
            radesys = "FK5"

    if radesys == 'FK4':
        if equinox is not None:
            equinox = Time(equinox, format='byear')
        frame = FK4(equinox=equinox)
    elif radesys == 'FK4-NO-E':
        if equinox is not None:
            equinox = Time(equinox, format='byear')
        frame = FK4NoETerms(equinox=equinox)
    elif radesys == 'FK5':
        if equinox is not None:
            equinox = Time(equinox, format='jyear')
        frame = FK5(equinox=equinox)
    elif radesys == 'ICRS':
        frame = ICRS()
    else:
        if xcoord == 'GLON' and ycoord == 'GLAT':
            frame = Galactic()
        elif xcoord == 'TLON' and ycoord == 'TLAT':
            frame = ITRS(obstime=wcs.wcs.dateobs or None)
        else:
            frame = None

    return frame


def _celestial_frame_to_wcs_builtin(frame, projection='TAN'):

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import BaseRADecFrame, FK4, FK4NoETerms, FK5, ICRS, ITRS, Galactic

    # Create a 2-dimensional WCS
    wcs = WCS(naxis=2)

    if isinstance(frame, BaseRADecFrame):

        xcoord = 'RA--'
        ycoord = 'DEC-'
        if isinstance(frame, ICRS):
            wcs.wcs.radesys = 'ICRS'
        elif isinstance(frame, FK4NoETerms):
            wcs.wcs.radesys = 'FK4-NO-E'
            wcs.wcs.equinox = frame.equinox.byear
        elif isinstance(frame, FK4):
            wcs.wcs.radesys = 'FK4'
            wcs.wcs.equinox = frame.equinox.byear
        elif isinstance(frame, FK5):
            wcs.wcs.radesys = 'FK5'
            wcs.wcs.equinox = frame.equinox.jyear
        else:
            return None
    elif isinstance(frame, Galactic):
        xcoord = 'GLON'
        ycoord = 'GLAT'
    elif isinstance(frame, ITRS):
        xcoord = 'TLON'
        ycoord = 'TLAT'
        wcs.wcs.radesys = 'ITRS'
        wcs.wcs.dateobs = frame.obstime.utc.isot
    else:
        return None

    wcs.wcs.ctype = [xcoord + '-' + projection, ycoord + '-' + projection]

    return wcs


WCS_FRAME_MAPPINGS = [[_wcs_to_celestial_frame_builtin]]
FRAME_WCS_MAPPINGS = [[_celestial_frame_to_wcs_builtin]]


class custom_wcs_to_frame_mappings:
    def __init__(self, mappings=[]):
        if hasattr(mappings, '__call__'):
            mappings = [mappings]
        WCS_FRAME_MAPPINGS.append(mappings)

    def __enter__(self):
        pass

    def __exit__(self, type, value, tb):
        WCS_FRAME_MAPPINGS.pop()


# Backward-compatibility
custom_frame_mappings = custom_wcs_to_frame_mappings


class custom_frame_to_wcs_mappings:
    def __init__(self, mappings=[]):
        if hasattr(mappings, '__call__'):
            mappings = [mappings]
        FRAME_WCS_MAPPINGS.append(mappings)

    def __enter__(self):
        pass

    def __exit__(self, type, value, tb):
        FRAME_WCS_MAPPINGS.pop()


def wcs_to_celestial_frame(wcs):
    """
    For a given WCS, return the coordinate frame that matches the celestial
    component of the WCS.

    Parameters
    ----------
    wcs : :class:`~astropy.wcs.WCS` instance
        The WCS to find the frame for

    Returns
    -------
    frame : :class:`~astropy.coordinates.baseframe.BaseCoordinateFrame` subclass instance
        An instance of a :class:`~astropy.coordinates.baseframe.BaseCoordinateFrame`
        subclass instance that best matches the specified WCS.

    Notes
    -----

    To extend this function to frames not defined in astropy.coordinates, you
    can write your own function which should take a :class:`~astropy.wcs.WCS`
    instance and should return either an instance of a frame, or `None` if no
    matching frame was found. You can register this function temporarily with::

        >>> from astropy.wcs.utils import wcs_to_celestial_frame, custom_wcs_to_frame_mappings
        >>> with custom_wcs_to_frame_mappings(my_function):
        ...     wcs_to_celestial_frame(...)

    """
    for mapping_set in WCS_FRAME_MAPPINGS:
        for func in mapping_set:
            frame = func(wcs)
            if frame is not None:
                return frame
    raise ValueError("Could not determine celestial frame corresponding to "
                     "the specified WCS object")


def celestial_frame_to_wcs(frame, projection='TAN'):
    """
    For a given coordinate frame, return the corresponding WCS object.

    Note that the returned WCS object has only the elements corresponding to
    coordinate frames set (e.g. ctype, equinox, radesys).

    Parameters
    ----------
    frame : :class:`~astropy.coordinates.baseframe.BaseCoordinateFrame` subclass instance
        An instance of a :class:`~astropy.coordinates.baseframe.BaseCoordinateFrame`
        subclass instance for which to find the WCS
    projection : str
        Projection code to use in ctype, if applicable

    Returns
    -------
    wcs : :class:`~astropy.wcs.WCS` instance
        The corresponding WCS object

    Examples
    --------

    ::

        >>> from astropy.wcs.utils import celestial_frame_to_wcs
        >>> from astropy.coordinates import FK5
        >>> frame = FK5(equinox='J2010')
        >>> wcs = celestial_frame_to_wcs(frame)
        >>> wcs.to_header()
        WCSAXES =                    2 / Number of coordinate axes
        CRPIX1  =                  0.0 / Pixel coordinate of reference point
        CRPIX2  =                  0.0 / Pixel coordinate of reference point
        CDELT1  =                  1.0 / [deg] Coordinate increment at reference point
        CDELT2  =                  1.0 / [deg] Coordinate increment at reference point
        CUNIT1  = 'deg'                / Units of coordinate increment and value
        CUNIT2  = 'deg'                / Units of coordinate increment and value
        CTYPE1  = 'RA---TAN'           / Right ascension, gnomonic projection
        CTYPE2  = 'DEC--TAN'           / Declination, gnomonic projection
        CRVAL1  =                  0.0 / [deg] Coordinate value at reference point
        CRVAL2  =                  0.0 / [deg] Coordinate value at reference point
        LONPOLE =                180.0 / [deg] Native longitude of celestial pole
        LATPOLE =                  0.0 / [deg] Native latitude of celestial pole
        RADESYS = 'FK5'                / Equatorial coordinate system
        EQUINOX =               2010.0 / [yr] Equinox of equatorial coordinates


    Notes
    -----

    To extend this function to frames not defined in astropy.coordinates, you
    can write your own function which should take a
    :class:`~astropy.coordinates.baseframe.BaseCoordinateFrame` subclass
    instance and a projection (given as a string) and should return either a WCS
    instance, or `None` if the WCS could not be determined. You can register
    this function temporarily with::

        >>> from astropy.wcs.utils import celestial_frame_to_wcs, custom_frame_to_wcs_mappings
        >>> with custom_frame_to_wcs_mappings(my_function):
        ...     celestial_frame_to_wcs(...)

    """
    for mapping_set in FRAME_WCS_MAPPINGS:
        for func in mapping_set:
            wcs = func(frame, projection=projection)
            if wcs is not None:
                return wcs
    raise ValueError("Could not determine WCS corresponding to the specified "
                     "coordinate frame.")


def proj_plane_pixel_scales(wcs):
    """
    For a WCS returns pixel scales along each axis of the image pixel at
    the ``CRPIX`` location once it is projected onto the
    "plane of intermediate world coordinates" as defined in
    `Greisen & Calabretta 2002, A&A, 395, 1061 <http://adsabs.harvard.edu/abs/2002A%26A...395.1061G>`_.

    .. note::
        This function is concerned **only** about the transformation
        "image plane"->"projection plane" and **not** about the
        transformation "celestial sphere"->"projection plane"->"image plane".
        Therefore, this function ignores distortions arising due to
        non-linear nature of most projections.

    .. note::
        In order to compute the scales corresponding to celestial axes only,
        make sure that the input `~astropy.wcs.WCS` object contains
        celestial axes only, e.g., by passing in the
        `~astropy.wcs.WCS.celestial` WCS object.

    Parameters
    ----------
    wcs : `~astropy.wcs.WCS`
        A world coordinate system object.

    Returns
    -------
    scale : `~numpy.ndarray`
        A vector (`~numpy.ndarray`) of projection plane increments
        corresponding to each pixel side (axis). The units of the returned
        results are the same as the units of `~astropy.wcs.Wcsprm.cdelt`,
        `~astropy.wcs.Wcsprm.crval`, and `~astropy.wcs.Wcsprm.cd` for
        the celestial WCS and can be obtained by inquiring the value
        of `~astropy.wcs.Wcsprm.cunit` property of the input
        `~astropy.wcs.WCS` WCS object.

    See Also
    --------
    astropy.wcs.utils.proj_plane_pixel_area

    """
    return np.sqrt((wcs.pixel_scale_matrix**2).sum(axis=0, dtype=float))


def proj_plane_pixel_area(wcs):
    """
    For a **celestial** WCS (see `astropy.wcs.WCS.celestial`) returns pixel
    area of the image pixel at the ``CRPIX`` location once it is projected
    onto the "plane of intermediate world coordinates" as defined in
    `Greisen & Calabretta 2002, A&A, 395, 1061 <http://adsabs.harvard.edu/abs/2002A%26A...395.1061G>`_.

    .. note::
        This function is concerned **only** about the transformation
        "image plane"->"projection plane" and **not** about the
        transformation "celestial sphere"->"projection plane"->"image plane".
        Therefore, this function ignores distortions arising due to
        non-linear nature of most projections.

    .. note::
        In order to compute the area of pixels corresponding to celestial
        axes only, this function uses the `~astropy.wcs.WCS.celestial` WCS
        object of the input ``wcs``.  This is different from the
        `~astropy.wcs.utils.proj_plane_pixel_scales` function
        that computes the scales for the axes of the input WCS itself.

    Parameters
    ----------
    wcs : `~astropy.wcs.WCS`
        A world coordinate system object.

    Returns
    -------
    area : float
        Area (in the projection plane) of the pixel at ``CRPIX`` location.
        The units of the returned result are the same as the units of
        the `~astropy.wcs.Wcsprm.cdelt`, `~astropy.wcs.Wcsprm.crval`,
        and `~astropy.wcs.Wcsprm.cd` for the celestial WCS and can be
        obtained by inquiring the value of `~astropy.wcs.Wcsprm.cunit`
        property of the `~astropy.wcs.WCS.celestial` WCS object.

    Raises
    ------
    ValueError
        Pixel area is defined only for 2D pixels. Most likely the
        `~astropy.wcs.Wcsprm.cd` matrix of the `~astropy.wcs.WCS.celestial`
        WCS is not a square matrix of second order.

    Notes
    -----

    Depending on the application, square root of the pixel area can be used to
    represent a single pixel scale of an equivalent square pixel
    whose area is equal to the area of a generally non-square pixel.

    See Also
    --------
    astropy.wcs.utils.proj_plane_pixel_scales

    """
    psm = wcs.celestial.pixel_scale_matrix
    if psm.shape != (2, 2):
        raise ValueError("Pixel area is defined only for 2D pixels.")
    return np.abs(np.linalg.det(psm))


def is_proj_plane_distorted(wcs, maxerr=1.0e-5):
    r"""
    For a WCS returns `False` if square image (detector) pixels stay square
    when projected onto the "plane of intermediate world coordinates"
    as defined in
    `Greisen & Calabretta 2002, A&A, 395, 1061 <http://adsabs.harvard.edu/abs/2002A%26A...395.1061G>`_.
    It will return `True` if transformation from image (detector) coordinates
    to the focal plane coordinates is non-orthogonal or if WCS contains
    non-linear (e.g., SIP) distortions.

    .. note::
        Since this function is concerned **only** about the transformation
        "image plane"->"focal plane" and **not** about the transformation
        "celestial sphere"->"focal plane"->"image plane",
        this function ignores distortions arising due to non-linear nature
        of most projections.

    Let's denote by *C* either the original or the reconstructed
    (from ``PC`` and ``CDELT``) CD matrix. `is_proj_plane_distorted`
    verifies that the transformation from image (detector) coordinates
    to the focal plane coordinates is orthogonal using the following
    check:

    .. math::
        \left \| \frac{C \cdot C^{\mathrm{T}}}
        {| det(C)|} - I \right \|_{\mathrm{max}} < \epsilon .

    Parameters
    ----------
    wcs : `~astropy.wcs.WCS`
        World coordinate system object

    maxerr : float, optional
        Accuracy to which the CD matrix, **normalized** such
        that :math:`|det(CD)|=1`, should be close to being an
        orthogonal matrix as described in the above equation
        (see :math:`\epsilon`).

    Returns
    -------
    distorted : bool
        Returns `True` if focal (projection) plane is distorted and `False`
        otherwise.

    """
    cwcs = wcs.celestial
    return (not _is_cd_orthogonal(cwcs.pixel_scale_matrix, maxerr) or
            _has_distortion(cwcs))


def _is_cd_orthogonal(cd, maxerr):
    shape = cd.shape
    if not (len(shape) == 2 and shape[0] == shape[1]):
        raise ValueError("CD (or PC) matrix must be a 2D square matrix.")

    pixarea = np.abs(np.linalg.det(cd))
    if (pixarea == 0.0):
        raise ValueError("CD (or PC) matrix is singular.")

    # NOTE: Technically, below we should use np.dot(cd, np.conjugate(cd.T))
    # However, I am not aware of complex CD/PC matrices...
    I = np.dot(cd, cd.T) / pixarea
    cd_unitary_err = np.amax(np.abs(I - np.eye(shape[0])))

    return (cd_unitary_err < maxerr)


def non_celestial_pixel_scales(inwcs):
    """
    Calculate the pixel scale along each axis of a non-celestial WCS,
    for example one with mixed spectral and spatial axes.

    Parameters
    ----------
    inwcs : `~astropy.wcs.WCS`
        The world coordinate system object.

    Returns
    -------
    scale : `numpy.ndarray`
        The pixel scale along each axis.
    """

    if inwcs.is_celestial:
        raise ValueError("WCS is celestial, use celestial_pixel_scales instead")

    pccd = inwcs.pixel_scale_matrix

    if np.allclose(np.extract(1-np.eye(*pccd.shape), pccd), 0):
        return np.abs(np.diagonal(pccd))*u.deg
    else:
        raise ValueError("WCS is rotated, cannot determine consistent pixel scales")


def _has_distortion(wcs):
    """
    `True` if contains any SIP or image distortion components.
    """
    return any(getattr(wcs, dist_attr) is not None
               for dist_attr in ['cpdis1', 'cpdis2', 'det2im1', 'det2im2', 'sip'])


# TODO: in future, we should think about how the following two functions can be
# integrated better into the WCS class.

def skycoord_to_pixel(coords, wcs, origin=0, mode='all'):
    """
    Convert a set of SkyCoord coordinates into pixels.

    Parameters
    ----------
    coords : `~astropy.coordinates.SkyCoord`
        The coordinates to convert.
    wcs : `~astropy.wcs.WCS`
        The WCS transformation to use.
    origin : int
        Whether to return 0 or 1-based pixel coordinates.
    mode : 'all' or 'wcs'
        Whether to do the transformation including distortions (``'all'``) or
        only including only the core WCS transformation (``'wcs'``).

    Returns
    -------
    xp, yp : `numpy.ndarray`
        The pixel coordinates

    See Also
    --------
    astropy.coordinates.SkyCoord.from_pixel
    """

    if _has_distortion(wcs) and wcs.naxis != 2:
        raise ValueError("Can only handle WCS with distortions for 2-dimensional WCS")

    # Keep only the celestial part of the axes, also re-orders lon/lat
    wcs = wcs.sub([WCSSUB_LONGITUDE, WCSSUB_LATITUDE])

    if wcs.naxis != 2:
        raise ValueError("WCS should contain celestial component")

    # Check which frame the WCS uses
    frame = wcs_to_celestial_frame(wcs)

    # Check what unit the WCS needs
    xw_unit = u.Unit(wcs.wcs.cunit[0])
    yw_unit = u.Unit(wcs.wcs.cunit[1])

    # Convert positions to frame
    coords = coords.transform_to(frame)

    # Extract longitude and latitude. We first try and use lon/lat directly,
    # but if the representation is not spherical or unit spherical this will
    # fail. We should then force the use of the unit spherical
    # representation. We don't do that directly to make sure that we preserve
    # custom lon/lat representations if available.
    try:
        lon = coords.data.lon.to(xw_unit)
        lat = coords.data.lat.to(yw_unit)
    except AttributeError:
        lon = coords.spherical.lon.to(xw_unit)
        lat = coords.spherical.lat.to(yw_unit)

    # Convert to pixel coordinates
    if mode == 'all':
        xp, yp = wcs.all_world2pix(lon.value, lat.value, origin)
    elif mode == 'wcs':
        xp, yp = wcs.wcs_world2pix(lon.value, lat.value, origin)
    else:
        raise ValueError("mode should be either 'all' or 'wcs'")

    return xp, yp


def pixel_to_skycoord(xp, yp, wcs, origin=0, mode='all', cls=None):
    """
    Convert a set of pixel coordinates into a `~astropy.coordinates.SkyCoord`
    coordinate.

    Parameters
    ----------
    xp, yp : float or `numpy.ndarray`
        The coordinates to convert.
    wcs : `~astropy.wcs.WCS`
        The WCS transformation to use.
    origin : int
        Whether to return 0 or 1-based pixel coordinates.
    mode : 'all' or 'wcs'
        Whether to do the transformation including distortions (``'all'``) or
        only including only the core WCS transformation (``'wcs'``).
    cls : class or None
        The class of object to create.  Should be a
        `~astropy.coordinates.SkyCoord` subclass.  If None, defaults to
        `~astropy.coordinates.SkyCoord`.

    Returns
    -------
    coords : Whatever ``cls`` is (a subclass of `~astropy.coordinates.SkyCoord`)
        The celestial coordinates

    See Also
    --------
    astropy.coordinates.SkyCoord.from_pixel
    """

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import SkyCoord, UnitSphericalRepresentation

    # we have to do this instead of actually setting the default to SkyCoord
    # because importing SkyCoord at the module-level leads to circular
    # dependencies.
    if cls is None:
        cls = SkyCoord

    if _has_distortion(wcs) and wcs.naxis != 2:
        raise ValueError("Can only handle WCS with distortions for 2-dimensional WCS")

    # Keep only the celestial part of the axes, also re-orders lon/lat
    wcs = wcs.sub([WCSSUB_LONGITUDE, WCSSUB_LATITUDE])

    if wcs.naxis != 2:
        raise ValueError("WCS should contain celestial component")

    # Check which frame the WCS uses
    frame = wcs_to_celestial_frame(wcs)

    # Check what unit the WCS gives
    lon_unit = u.Unit(wcs.wcs.cunit[0])
    lat_unit = u.Unit(wcs.wcs.cunit[1])

    # Convert pixel coordinates to celestial coordinates
    if mode == 'all':
        lon, lat = wcs.all_pix2world(xp, yp, origin)
    elif mode == 'wcs':
        lon, lat = wcs.wcs_pix2world(xp, yp, origin)
    else:
        raise ValueError("mode should be either 'all' or 'wcs'")

    # Add units to longitude/latitude
    lon = lon * lon_unit
    lat = lat * lat_unit

    # Create a SkyCoord-like object
    data = UnitSphericalRepresentation(lon=lon, lat=lat)
    coords = cls(frame.realize_frame(data))

    return coords


def _unique_with_order_preserved(items):
    """
    Return a list of unique items in the list provided, preserving the order
    in which they are found.
    """
    new_items = []
    for item in items:
        if item not in new_items:
            new_items.append(item)
    return new_items


def _pixel_to_world_correlation_matrix(wcs):
    """
    Return a correlation matrix between the pixel coordinates and the
    high level world coordinates, along with the list of high level world
    coordinate classes.

    The shape of the matrix is ``(n_world, n_pix)``, where ``n_world`` is the
    number of high level world coordinates.
    """

    # We basically want to collapse the world dimensions together that are
    # combined into the same high-level objects.

    # Get the following in advance as getting these properties can be expensive
    all_components = wcs.low_level_wcs.world_axis_object_components
    all_classes = wcs.low_level_wcs.world_axis_object_classes
    axis_correlation_matrix = wcs.low_level_wcs.axis_correlation_matrix

    components = _unique_with_order_preserved([c[0] for c in all_components])

    matrix = np.zeros((len(components), wcs.pixel_n_dim), dtype=bool)

    for iworld in range(wcs.world_n_dim):
        iworld_unique = components.index(all_components[iworld][0])
        matrix[iworld_unique] |= axis_correlation_matrix[iworld]

    classes = [all_classes[component][0] for component in components]

    return matrix, classes


def _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out):
    """
    Correlation matrix between the input and output pixel coordinates for a
    pixel -> world -> pixel transformation specified by two WCS instances.

    The first WCS specified is the one used for the pixel -> world
    transformation and the second WCS specified is the one used for the world ->
    pixel transformation. The shape of the matrix is
    ``(n_pixel_out, n_pixel_in)``.
    """

    matrix1, classes1 = _pixel_to_world_correlation_matrix(wcs_in)
    matrix2, classes2 = _pixel_to_world_correlation_matrix(wcs_out)

    if len(classes1) != len(classes2):
        raise ValueError("The two WCS return a different number of world coordinates")

    # Check if classes match uniquely
    unique_match = True
    mapping = []
    for class1 in classes1:
        matches = classes2.count(class1)
        if matches == 0:
            raise ValueError("The world coordinate types of the two WCS do not match")
        elif matches > 1:
            unique_match = False
            break
        else:
            mapping.append(classes2.index(class1))

    if unique_match:

        # Classes are unique, so we need to re-order matrix2 along the world
        # axis using the mapping we found above.
        matrix2 = matrix2[mapping]

    elif classes1 != classes2:

        raise ValueError("World coordinate order doesn't match and automatic matching is ambiguous")

    matrix = np.matmul(matrix2.T, matrix1)

    return matrix


def _split_matrix(matrix):
    """
    Given an axis correlation matrix from a WCS object, return information about
    the individual WCS that can be split out.

    The output is a list of tuples, where each tuple contains a list of
    pixel dimensions and a list of world dimensions that can be extracted to
    form a new WCS. For example, in the case of a spectral cube with the first
    two world coordinates being the celestial coordinates and the third
    coordinate being an uncorrelated spectral axis, the matrix would look like::

        array([[ True,  True, False],
               [ True,  True, False],
               [False, False,  True]])

    and this function will return ``[([0, 1], [0, 1]), ([2], [2])]``.
    """

    pixel_used = []

    split_info = []

    for ipix in range(matrix.shape[1]):
        if ipix in pixel_used:
            continue
        pixel_include = np.zeros(matrix.shape[1], dtype=bool)
        pixel_include[ipix] = True
        n_pix_prev, n_pix = 0, 1
        while n_pix > n_pix_prev:
            world_include = matrix[:, pixel_include].any(axis=1)
            pixel_include = matrix[world_include, :].any(axis=0)
            n_pix_prev, n_pix = n_pix, np.sum(pixel_include)
        pixel_indices = list(np.nonzero(pixel_include)[0])
        world_indices = list(np.nonzero(world_include)[0])
        pixel_used.extend(pixel_indices)
        split_info.append((pixel_indices, world_indices))

    return split_info


def pixel_to_pixel(wcs_in, wcs_out, *inputs):
    """
    Transform pixel coordinates in a dataset with a WCS to pixel coordinates
    in another dataset with a different WCS.

    This function is designed to efficiently deal with input pixel arrays that
    are broadcasted views of smaller arrays, and is compatible with any
    APE14-compliant WCS.

    Parameters
    ----------
    wcs_in : `~astropy.wcs.wcsapi.BaseHighLevelWCS`
        A WCS object for the original dataset which complies with the
        high-level shared APE 14 WCS API.
    wcs_out : `~astropy.wcs.wcsapi.BaseHighLevelWCS`
        A WCS object for the target dataset which complies with the
        high-level shared APE 14 WCS API.
    *inputs :
        Scalars or arrays giving the pixel coordinates to transform.
    """

    # Shortcut for scalars
    if np.isscalar(inputs[0]):
        world_outputs = wcs_in.pixel_to_world(*inputs)
        if not isinstance(world_outputs, (tuple, list)):
            world_outputs = (world_outputs,)
        return wcs_out.world_to_pixel(*world_outputs)

    # Remember original shape
    original_shape = inputs[0].shape

    matrix = _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out)
    split_info = _split_matrix(matrix)

    outputs = [None] * wcs_out.pixel_n_dim

    for (pixel_in_indices, pixel_out_indices) in split_info:

        pixel_inputs = []
        for ipix in range(wcs_in.pixel_n_dim):
            if ipix in pixel_in_indices:
                pixel_inputs.append(unbroadcast(inputs[ipix]))
            else:
                pixel_inputs.append(inputs[ipix].flat[0])

        pixel_inputs = np.broadcast_arrays(*pixel_inputs)

        world_outputs = wcs_in.pixel_to_world(*pixel_inputs)

        if not isinstance(world_outputs, (tuple, list)):
            world_outputs = (world_outputs,)

        pixel_outputs = wcs_out.world_to_pixel(*world_outputs)

        if wcs_out.pixel_n_dim == 1:
            pixel_outputs = (pixel_outputs,)

        for ipix in range(wcs_out.pixel_n_dim):
            if ipix in pixel_out_indices:
                outputs[ipix] = np.broadcast_to(pixel_outputs[ipix], original_shape)

    return outputs[0] if wcs_out.pixel_n_dim == 1 else outputs


def local_partial_pixel_derivatives(wcs, *pixel, normalize_by_world=False):
    """
    Return a matrix of shape ``(world_n_dim, pixel_n_dim)`` where each entry
    ``[i, j]`` is the partial derivative d(world_i)/d(pixel_j) at the requested
    pixel position.

    Parameters
    ----------
    wcs : `~astropy.wcs.WCS`
        The WCS transformation to evaluate the derivatives for.
    *pixel : float
        The scalar pixel coordinates at which to evaluate the derivatives.
    normalize_by_world : bool
        If `True`, the matrix is normalized so that for each world entry
        the derivatives add up to 1.
    """

    # Find the world coordinates at the requested pixel
    pixel_ref = np.array(pixel)
    world_ref = np.array(wcs.pixel_to_world_values(*pixel_ref))

    # Set up the derivative matrix
    derivatives = np.zeros((wcs.world_n_dim, wcs.pixel_n_dim))

    for i in range(wcs.pixel_n_dim):
        pixel_off = pixel_ref.copy()
        pixel_off[i] += 1
        world_off = np.array(wcs.pixel_to_world_values(*pixel_off))
        derivatives[:, i] = world_off - world_ref

    if normalize_by_world:
        derivatives /= derivatives.sum(axis=0)[:, np.newaxis]

    return derivatives

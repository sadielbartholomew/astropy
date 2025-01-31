# Licensed under a 3-clause BSD style license - see LICENSE.rst

import warnings

import pytest

import numpy as np
from numpy.testing import assert_almost_equal, assert_equal, assert_allclose

from astropy.utils.data import get_pkg_data_contents, get_pkg_data_filename
from astropy.utils.exceptions import AstropyUserWarning
from astropy.time import Time
from astropy import units as u
from astropy.utils.misc import unbroadcast
from astropy.coordinates import SkyCoord
from astropy.units import Quantity

from astropy.wcs.wcs import (WCS, Sip, WCSSUB_LONGITUDE, WCSSUB_LATITUDE,
                             FITSFixedWarning)
from astropy.wcs.wcsapi.fitswcs import SlicedFITSWCS
from astropy.wcs.utils import (proj_plane_pixel_scales,
                               is_proj_plane_distorted,
                               non_celestial_pixel_scales,
                               wcs_to_celestial_frame,
                               celestial_frame_to_wcs, skycoord_to_pixel,
                               pixel_to_skycoord, custom_wcs_to_frame_mappings,
                               custom_frame_to_wcs_mappings,
                               add_stokes_axis_to_wcs,
                               pixel_to_pixel,
                               _split_matrix,
                               _pixel_to_pixel_correlation_matrix,
                               _pixel_to_world_correlation_matrix,
                               local_partial_pixel_derivatives)


def test_wcs_dropping():
    wcs = WCS(naxis=4)
    wcs.wcs.pc = np.zeros([4, 4])
    np.fill_diagonal(wcs.wcs.pc, np.arange(1, 5))
    pc = wcs.wcs.pc  # for later use below

    dropped = wcs.dropaxis(0)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([2, 3, 4]))
    dropped = wcs.dropaxis(1)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([1, 3, 4]))
    dropped = wcs.dropaxis(2)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([1, 2, 4]))
    dropped = wcs.dropaxis(3)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([1, 2, 3]))

    wcs = WCS(naxis=4)
    wcs.wcs.cd = pc

    dropped = wcs.dropaxis(0)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([2, 3, 4]))
    dropped = wcs.dropaxis(1)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([1, 3, 4]))
    dropped = wcs.dropaxis(2)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([1, 2, 4]))
    dropped = wcs.dropaxis(3)
    assert np.all(dropped.wcs.get_pc().diagonal() == np.array([1, 2, 3]))


def test_wcs_swapping():
    wcs = WCS(naxis=4)
    wcs.wcs.pc = np.zeros([4, 4])
    np.fill_diagonal(wcs.wcs.pc, np.arange(1, 5))
    pc = wcs.wcs.pc  # for later use below

    swapped = wcs.swapaxes(0, 1)
    assert np.all(swapped.wcs.get_pc().diagonal() == np.array([2, 1, 3, 4]))
    swapped = wcs.swapaxes(0, 3)
    assert np.all(swapped.wcs.get_pc().diagonal() == np.array([4, 2, 3, 1]))
    swapped = wcs.swapaxes(2, 3)
    assert np.all(swapped.wcs.get_pc().diagonal() == np.array([1, 2, 4, 3]))

    wcs = WCS(naxis=4)
    wcs.wcs.cd = pc

    swapped = wcs.swapaxes(0, 1)
    assert np.all(swapped.wcs.get_pc().diagonal() == np.array([2, 1, 3, 4]))
    swapped = wcs.swapaxes(0, 3)
    assert np.all(swapped.wcs.get_pc().diagonal() == np.array([4, 2, 3, 1]))
    swapped = wcs.swapaxes(2, 3)
    assert np.all(swapped.wcs.get_pc().diagonal() == np.array([1, 2, 4, 3]))


@pytest.mark.parametrize('ndim', (2, 3))
def test_add_stokes(ndim):
    wcs = WCS(naxis=ndim)

    for ii in range(ndim + 1):
        outwcs = add_stokes_axis_to_wcs(wcs, ii)
        assert outwcs.wcs.naxis == ndim + 1
        assert outwcs.wcs.ctype[ii] == 'STOKES'
        assert outwcs.wcs.cname[ii] == 'STOKES'


def test_slice():
    mywcs = WCS(naxis=2)
    mywcs.wcs.crval = [1, 1]
    mywcs.wcs.cdelt = [0.1, 0.1]
    mywcs.wcs.crpix = [1, 1]
    mywcs._naxis = [1000, 500]
    pscale = 0.1  # from cdelt

    slice_wcs = mywcs.slice([slice(1, None), slice(0, None)])
    assert np.all(slice_wcs.wcs.crpix == np.array([1, 0]))
    assert slice_wcs._naxis == [1000, 499]

    # test that CRPIX maps to CRVAL:
    assert_allclose(
        slice_wcs.wcs_pix2world(*slice_wcs.wcs.crpix, 1),
        slice_wcs.wcs.crval, rtol=0.0, atol=1e-6 * pscale
    )

    slice_wcs = mywcs.slice([slice(1, None, 2), slice(0, None, 4)])
    assert np.all(slice_wcs.wcs.crpix == np.array([0.625, 0.25]))
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.4, 0.2]))
    assert slice_wcs._naxis == [250, 250]

    slice_wcs = mywcs.slice([slice(None, None, 2), slice(0, None, 2)])
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.2, 0.2]))
    assert slice_wcs._naxis == [500, 250]

    # Non-integral values do not alter the naxis attribute
    with pytest.warns(AstropyUserWarning):
        slice_wcs = mywcs.slice([slice(50.), slice(20.)])
    assert slice_wcs._naxis == [1000, 500]
    with pytest.warns(AstropyUserWarning):
        slice_wcs = mywcs.slice([slice(50.), slice(20)])
    assert slice_wcs._naxis == [20, 500]
    with pytest.warns(AstropyUserWarning):
        slice_wcs = mywcs.slice([slice(50), slice(20.5)])
    assert slice_wcs._naxis == [1000, 50]


def test_slice_with_sip():
    mywcs = WCS(naxis=2)
    mywcs.wcs.crval = [1, 1]
    mywcs.wcs.cdelt = [0.1, 0.1]
    mywcs.wcs.crpix = [1, 1]
    mywcs._naxis = [1000, 500]
    mywcs.wcs.ctype = ['RA---TAN-SIP', 'DEC--TAN-SIP']
    a = np.array(
        [[0, 0, 5.33092692e-08, 3.73753773e-11, -2.02111473e-13],
         [0, 2.44084308e-05, 2.81394789e-11, 5.17856895e-13, 0.0],
         [-2.41334657e-07, 1.29289255e-10, 2.35753629e-14, 0.0, 0.0],
         [-2.37162007e-10, 5.43714947e-13, 0.0, 0.0, 0.0],
         [-2.81029767e-13, 0.0, 0.0, 0.0, 0.0]]
    )
    b = np.array(
        [[0, 0, 2.99270374e-05, -2.38136074e-10, 7.23205168e-13],
         [0, -1.71073858e-07, 6.31243431e-11, -5.16744347e-14, 0.0],
         [6.95458963e-06, -3.08278961e-10, -1.75800917e-13, 0.0, 0.0],
         [3.51974159e-11, 5.60993016e-14, 0.0, 0.0, 0.0],
         [-5.92438525e-13, 0.0, 0.0, 0.0, 0.0]]
    )
    mywcs.sip = Sip(a, b, None, None, mywcs.wcs.crpix)
    mywcs.wcs.set()
    pscale = 0.1  # from cdelt

    slice_wcs = mywcs.slice([slice(1, None), slice(0, None)])
    # test that CRPIX maps to CRVAL:
    assert_allclose(
        slice_wcs.all_pix2world(*slice_wcs.wcs.crpix, 1),
        slice_wcs.wcs.crval, rtol=0.0, atol=1e-6 * pscale
    )

    slice_wcs = mywcs.slice([slice(1, None, 2), slice(0, None, 4)])
    # test that CRPIX maps to CRVAL:
    assert_allclose(
        slice_wcs.all_pix2world(*slice_wcs.wcs.crpix, 1),
        slice_wcs.wcs.crval, rtol=0.0, atol=1e-6 * pscale
    )


def test_slice_getitem():
    mywcs = WCS(naxis=2)
    mywcs.wcs.crval = [1, 1]
    mywcs.wcs.cdelt = [0.1, 0.1]
    mywcs.wcs.crpix = [1, 1]

    slice_wcs = mywcs[1::2, 0::4]
    assert np.all(slice_wcs.wcs.crpix == np.array([0.625, 0.25]))
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.4, 0.2]))

    mywcs.wcs.crpix = [2, 2]
    slice_wcs = mywcs[1::2, 0::4]
    assert np.all(slice_wcs.wcs.crpix == np.array([0.875, 0.75]))
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.4, 0.2]))

    # Default: numpy order
    slice_wcs = mywcs[1::2]
    assert np.all(slice_wcs.wcs.crpix == np.array([2, 0.75]))
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.1, 0.2]))


def test_slice_fitsorder():
    mywcs = WCS(naxis=2)
    mywcs.wcs.crval = [1, 1]
    mywcs.wcs.cdelt = [0.1, 0.1]
    mywcs.wcs.crpix = [1, 1]

    slice_wcs = mywcs.slice([slice(1, None), slice(0, None)], numpy_order=False)
    assert np.all(slice_wcs.wcs.crpix == np.array([0, 1]))

    slice_wcs = mywcs.slice([slice(1, None, 2), slice(0, None, 4)], numpy_order=False)
    assert np.all(slice_wcs.wcs.crpix == np.array([0.25, 0.625]))
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.2, 0.4]))

    slice_wcs = mywcs.slice([slice(1, None, 2)], numpy_order=False)
    assert np.all(slice_wcs.wcs.crpix == np.array([0.25, 1]))
    assert np.all(slice_wcs.wcs.cdelt == np.array([0.2, 0.1]))


def test_slice_wcs():
    mywcs = WCS(naxis=2)

    sub = mywcs[0]
    assert isinstance(sub, SlicedFITSWCS)

    with pytest.raises(IndexError) as exc:
        mywcs[0, ::2]
    assert exc.value.args[0] == "Slicing WCS with a step is not supported."


def test_axis_names():
    mywcs = WCS(naxis=4)
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN', 'VOPT-LSR', 'STOKES']

    assert mywcs.axis_type_names == ['RA', 'DEC', 'VOPT', 'STOKES']

    mywcs.wcs.cname = ['RA', 'DEC', 'VOPT', 'STOKES']

    assert mywcs.axis_type_names == ['RA', 'DEC', 'VOPT', 'STOKES']


def test_celestial():
    mywcs = WCS(naxis=4)
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN', 'VOPT', 'STOKES']
    cel = mywcs.celestial
    assert tuple(cel.wcs.ctype) == ('RA---TAN', 'DEC--TAN')
    assert cel.axis_type_names == ['RA', 'DEC']


def test_wcs_to_celestial_frame():

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates.builtin_frames import ICRS, ITRS, FK5, FK4, Galactic

    mywcs = WCS(naxis=2)
    mywcs.wcs.set()
    with pytest.raises(ValueError) as exc:
        assert wcs_to_celestial_frame(mywcs) is None
    assert exc.value.args[0] == "Could not determine celestial frame corresponding to the specified WCS object"

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['XOFFSET', 'YOFFSET']
    mywcs.wcs.set()
    with pytest.raises(ValueError):
        assert wcs_to_celestial_frame(mywcs) is None

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, ICRS)

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    mywcs.wcs.equinox = 1987.
    mywcs.wcs.set()
    print(mywcs.to_header())
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, FK5)
    assert frame.equinox == Time(1987., format='jyear')

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    mywcs.wcs.equinox = 1982
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, FK4)
    assert frame.equinox == Time(1982., format='byear')

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['GLON-SIN', 'GLAT-SIN']
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, Galactic)

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['TLON-CAR', 'TLAT-CAR']
    mywcs.wcs.dateobs = '2017-08-17T12:41:04.430'
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, ITRS)
    assert frame.obstime == Time('2017-08-17T12:41:04.430')

    for equinox in [np.nan, 1987, 1982]:
        mywcs = WCS(naxis=2)
        mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
        mywcs.wcs.radesys = 'ICRS'
        mywcs.wcs.equinox = equinox
        mywcs.wcs.set()
        frame = wcs_to_celestial_frame(mywcs)
        assert isinstance(frame, ICRS)

    # Flipped order
    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['DEC--TAN', 'RA---TAN']
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, ICRS)

    # More than two dimensions
    mywcs = WCS(naxis=3)
    mywcs.wcs.ctype = ['DEC--TAN', 'VELOCITY', 'RA---TAN']
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, ICRS)

    mywcs = WCS(naxis=3)
    mywcs.wcs.ctype = ['GLAT-CAR', 'VELOCITY', 'GLON-CAR']
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, Galactic)


def test_wcs_to_celestial_frame_correlated():

    # Regression test for a bug that caused wcs_to_celestial_frame to fail when
    # the celestial axes were correlated with other axes.

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates.builtin_frames import ICRS

    mywcs = WCS(naxis=3)
    mywcs.wcs.ctype = 'RA---TAN', 'DEC--TAN', 'FREQ'
    mywcs.wcs.cd = np.ones((3, 3))
    mywcs.wcs.set()
    frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, ICRS)


def test_wcs_to_celestial_frame_extend():

    mywcs = WCS(naxis=2)
    mywcs.wcs.ctype = ['XOFFSET', 'YOFFSET']
    mywcs.wcs.set()
    with pytest.raises(ValueError):
        wcs_to_celestial_frame(mywcs)

    class OffsetFrame:
        pass

    def identify_offset(wcs):
        if wcs.wcs.ctype[0].endswith('OFFSET') and wcs.wcs.ctype[1].endswith('OFFSET'):
            return OffsetFrame()

    with custom_wcs_to_frame_mappings(identify_offset):
        frame = wcs_to_celestial_frame(mywcs)
    assert isinstance(frame, OffsetFrame)

    # Check that things are back to normal after the context manager
    with pytest.raises(ValueError):
        wcs_to_celestial_frame(mywcs)


def test_celestial_frame_to_wcs():

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import ICRS, ITRS, FK5, FK4, FK4NoETerms, Galactic, BaseCoordinateFrame

    class FakeFrame(BaseCoordinateFrame):
        pass

    frame = FakeFrame()
    with pytest.raises(ValueError) as exc:
        celestial_frame_to_wcs(frame)
    assert exc.value.args[0] == ("Could not determine WCS corresponding to "
                                 "the specified coordinate frame.")

    frame = ICRS()
    mywcs = celestial_frame_to_wcs(frame)
    mywcs.wcs.set()
    assert tuple(mywcs.wcs.ctype) == ('RA---TAN', 'DEC--TAN')
    assert mywcs.wcs.radesys == 'ICRS'
    assert np.isnan(mywcs.wcs.equinox)
    assert mywcs.wcs.lonpole == 180
    assert mywcs.wcs.latpole == 0

    frame = FK5(equinox='J1987')
    mywcs = celestial_frame_to_wcs(frame)
    assert tuple(mywcs.wcs.ctype) == ('RA---TAN', 'DEC--TAN')
    assert mywcs.wcs.radesys == 'FK5'
    assert mywcs.wcs.equinox == 1987.

    frame = FK4(equinox='B1982')
    mywcs = celestial_frame_to_wcs(frame)
    assert tuple(mywcs.wcs.ctype) == ('RA---TAN', 'DEC--TAN')
    assert mywcs.wcs.radesys == 'FK4'
    assert mywcs.wcs.equinox == 1982.

    frame = FK4NoETerms(equinox='B1982')
    mywcs = celestial_frame_to_wcs(frame)
    assert tuple(mywcs.wcs.ctype) == ('RA---TAN', 'DEC--TAN')
    assert mywcs.wcs.radesys == 'FK4-NO-E'
    assert mywcs.wcs.equinox == 1982.

    frame = Galactic()
    mywcs = celestial_frame_to_wcs(frame)
    assert tuple(mywcs.wcs.ctype) == ('GLON-TAN', 'GLAT-TAN')
    assert mywcs.wcs.radesys == ''
    assert np.isnan(mywcs.wcs.equinox)

    frame = Galactic()
    mywcs = celestial_frame_to_wcs(frame, projection='CAR')
    assert tuple(mywcs.wcs.ctype) == ('GLON-CAR', 'GLAT-CAR')
    assert mywcs.wcs.radesys == ''
    assert np.isnan(mywcs.wcs.equinox)

    frame = Galactic()
    mywcs = celestial_frame_to_wcs(frame, projection='CAR')
    mywcs.wcs.crval = [100, -30]
    mywcs.wcs.set()
    assert_allclose((mywcs.wcs.lonpole, mywcs.wcs.latpole), (180, 60))

    frame = ITRS(obstime=Time('2017-08-17T12:41:04.43'))
    mywcs = celestial_frame_to_wcs(frame, projection='CAR')
    assert tuple(mywcs.wcs.ctype) == ('TLON-CAR', 'TLAT-CAR')
    assert mywcs.wcs.radesys == 'ITRS'
    assert mywcs.wcs.dateobs == '2017-08-17T12:41:04.430'

    frame = ITRS()
    mywcs = celestial_frame_to_wcs(frame, projection='CAR')
    assert tuple(mywcs.wcs.ctype) == ('TLON-CAR', 'TLAT-CAR')
    assert mywcs.wcs.radesys == 'ITRS'
    assert mywcs.wcs.dateobs == Time('J2000').utc.fits


def test_celestial_frame_to_wcs_extend():

    class OffsetFrame:
        pass

    frame = OffsetFrame()

    with pytest.raises(ValueError):
        celestial_frame_to_wcs(frame)

    def identify_offset(frame, projection=None):
        if isinstance(frame, OffsetFrame):
            wcs = WCS(naxis=2)
            wcs.wcs.ctype = ['XOFFSET', 'YOFFSET']
            return wcs

    with custom_frame_to_wcs_mappings(identify_offset):
        mywcs = celestial_frame_to_wcs(frame)
    assert tuple(mywcs.wcs.ctype) == ('XOFFSET', 'YOFFSET')

    # Check that things are back to normal after the context manager
    with pytest.raises(ValueError):
        celestial_frame_to_wcs(frame)


def test_pixscale_nodrop():
    mywcs = WCS(naxis=2)
    mywcs.wcs.cdelt = [0.1, 0.2]
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    assert_almost_equal(proj_plane_pixel_scales(mywcs), (0.1, 0.2))

    mywcs.wcs.cdelt = [-0.1, 0.2]
    assert_almost_equal(proj_plane_pixel_scales(mywcs), (0.1, 0.2))


def test_pixscale_withdrop():
    mywcs = WCS(naxis=3)
    mywcs.wcs.cdelt = [0.1, 0.2, 1]
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN', 'VOPT']
    assert_almost_equal(proj_plane_pixel_scales(mywcs.celestial), (0.1, 0.2))

    mywcs.wcs.cdelt = [-0.1, 0.2, 1]
    assert_almost_equal(proj_plane_pixel_scales(mywcs.celestial), (0.1, 0.2))


def test_pixscale_cd():
    mywcs = WCS(naxis=2)
    mywcs.wcs.cd = [[-0.1, 0], [0, 0.2]]
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    assert_almost_equal(proj_plane_pixel_scales(mywcs), (0.1, 0.2))


@pytest.mark.parametrize('angle',
                         (30, 45, 60, 75))
def test_pixscale_cd_rotated(angle):
    mywcs = WCS(naxis=2)
    rho = np.radians(angle)
    scale = 0.1
    mywcs.wcs.cd = [[scale * np.cos(rho), -scale * np.sin(rho)],
                    [scale * np.sin(rho), scale * np.cos(rho)]]
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    assert_almost_equal(proj_plane_pixel_scales(mywcs), (0.1, 0.1))


@pytest.mark.parametrize('angle',
                         (30, 45, 60, 75))
def test_pixscale_pc_rotated(angle):
    mywcs = WCS(naxis=2)
    rho = np.radians(angle)
    scale = 0.1
    mywcs.wcs.cdelt = [-scale, scale]
    mywcs.wcs.pc = [[np.cos(rho), -np.sin(rho)],
                    [np.sin(rho), np.cos(rho)]]
    mywcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    assert_almost_equal(proj_plane_pixel_scales(mywcs), (0.1, 0.1))


@pytest.mark.parametrize(('cdelt', 'pc', 'pccd'),
                         (([0.1, 0.2], np.eye(2), np.diag([0.1, 0.2])),
                          ([0.1, 0.2, 0.3], np.eye(3), np.diag([0.1, 0.2, 0.3])),
                          ([1, 1, 1], np.diag([0.1, 0.2, 0.3]), np.diag([0.1, 0.2, 0.3]))))
def test_pixel_scale_matrix(cdelt, pc, pccd):

    mywcs = WCS(naxis=(len(cdelt)))
    mywcs.wcs.cdelt = cdelt
    mywcs.wcs.pc = pc

    assert_almost_equal(mywcs.pixel_scale_matrix, pccd)


@pytest.mark.parametrize(('ctype', 'cel'),
                         ((['RA---TAN', 'DEC--TAN'], True),
                          (['RA---TAN', 'DEC--TAN', 'FREQ'], False),
                          (['RA---TAN', 'FREQ'], False),))
def test_is_celestial(ctype, cel):
    mywcs = WCS(naxis=len(ctype))
    mywcs.wcs.ctype = ctype

    assert mywcs.is_celestial == cel


@pytest.mark.parametrize(('ctype', 'cel'),
                         ((['RA---TAN', 'DEC--TAN'], True),
                          (['RA---TAN', 'DEC--TAN', 'FREQ'], True),
                          (['RA---TAN', 'FREQ'], False),))
def test_has_celestial(ctype, cel):
    mywcs = WCS(naxis=len(ctype))
    mywcs.wcs.ctype = ctype

    assert mywcs.has_celestial == cel


def test_has_celestial_correlated():
    # Regression test for astropy/astropy#8416 - has_celestial failed when
    # celestial axes were correlated with other axes.
    mywcs = WCS(naxis=3)
    mywcs.wcs.ctype = 'RA---TAN', 'DEC--TAN', 'FREQ'
    mywcs.wcs.cd = np.ones((3, 3))
    mywcs.wcs.set()
    assert mywcs.has_celestial


@pytest.mark.parametrize(('cdelt', 'pc', 'cd'),
                         ((np.array([0.1, 0.2]), np.eye(2), np.eye(2)),
                          (np.array([1, 1]), np.diag([0.1, 0.2]), np.eye(2)),
                          (np.array([0.1, 0.2]), np.eye(2), None),
                          (np.array([0.1, 0.2]), None, np.eye(2)),
                          ))
def test_noncelestial_scale(cdelt, pc, cd):

    mywcs = WCS(naxis=2)
    if cd is not None:
        mywcs.wcs.cd = cd
    if pc is not None:
        mywcs.wcs.pc = pc

    # TODO: Some inputs emit RuntimeWarning from here onwards.
    #       Fix the test data. See @nden's comment in PR 9010.
    mywcs.wcs.cdelt = cdelt

    mywcs.wcs.ctype = ['RA---TAN', 'FREQ']

    ps = non_celestial_pixel_scales(mywcs)

    assert_almost_equal(ps.to_value(u.deg), np.array([0.1, 0.2]))


@pytest.mark.parametrize('mode', ['all', 'wcs'])
def test_skycoord_to_pixel(mode):

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import SkyCoord

    header = get_pkg_data_contents('data/maps/1904-66_TAN.hdr', encoding='binary')
    wcs = WCS(header)

    ref = SkyCoord(0.1 * u.deg, -89. * u.deg, frame='icrs')

    xp, yp = skycoord_to_pixel(ref, wcs, mode=mode)

    # WCS is in FK5 so we need to transform back to ICRS
    new = pixel_to_skycoord(xp, yp, wcs, mode=mode).transform_to('icrs')

    assert_allclose(new.ra.degree, ref.ra.degree)
    assert_allclose(new.dec.degree, ref.dec.degree)

    # Make sure you can specify a different class using ``cls`` keyword
    class SkyCoord2(SkyCoord):
        pass

    new2 = pixel_to_skycoord(xp, yp, wcs, mode=mode,
                             cls=SkyCoord2).transform_to('icrs')

    assert new2.__class__ is SkyCoord2
    assert_allclose(new2.ra.degree, ref.ra.degree)
    assert_allclose(new2.dec.degree, ref.dec.degree)


def test_skycoord_to_pixel_swapped():

    # Regression test for a bug that caused skycoord_to_pixel and
    # pixel_to_skycoord to not work correctly if the axes were swapped in the
    # WCS.

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import SkyCoord

    header = get_pkg_data_contents('data/maps/1904-66_TAN.hdr', encoding='binary')
    wcs = WCS(header)

    wcs_swapped = wcs.sub([WCSSUB_LATITUDE, WCSSUB_LONGITUDE])

    ref = SkyCoord(0.1 * u.deg, -89. * u.deg, frame='icrs')

    xp1, yp1 = skycoord_to_pixel(ref, wcs)
    xp2, yp2 = skycoord_to_pixel(ref, wcs_swapped)

    assert_allclose(xp1, xp2)
    assert_allclose(yp1, yp2)

    # WCS is in FK5 so we need to transform back to ICRS
    new1 = pixel_to_skycoord(xp1, yp1, wcs).transform_to('icrs')
    new2 = pixel_to_skycoord(xp1, yp1, wcs_swapped).transform_to('icrs')

    assert_allclose(new1.ra.degree, new2.ra.degree)
    assert_allclose(new1.dec.degree, new2.dec.degree)


def test_is_proj_plane_distorted():
    # non-orthogonal CD:
    wcs = WCS(naxis=2)
    wcs.wcs.cd = [[-0.1, 0], [0, 0.2]]
    wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    assert(is_proj_plane_distorted(wcs))

    # almost orthogonal CD:
    wcs.wcs.cd = [[0.1 + 2.0e-7, 1.7e-7], [1.2e-7, 0.1 - 1.3e-7]]
    assert(not is_proj_plane_distorted(wcs))

    # real case:
    header = get_pkg_data_filename('data/sip.fits')
    with pytest.warns(FITSFixedWarning):
        wcs = WCS(header)
    assert(is_proj_plane_distorted(wcs))


@pytest.mark.parametrize('mode', ['all', 'wcs'])
def test_skycoord_to_pixel_distortions(mode):

    # Import astropy.coordinates here to avoid circular imports
    from astropy.coordinates import SkyCoord

    header = get_pkg_data_filename('data/sip.fits')
    with pytest.warns(FITSFixedWarning):
        wcs = WCS(header)

    ref = SkyCoord(202.50 * u.deg, 47.19 * u.deg, frame='icrs')

    xp, yp = skycoord_to_pixel(ref, wcs, mode=mode)

    # WCS is in FK5 so we need to transform back to ICRS
    new = pixel_to_skycoord(xp, yp, wcs, mode=mode).transform_to('icrs')

    assert_allclose(new.ra.degree, ref.ra.degree)
    assert_allclose(new.dec.degree, ref.dec.degree)


@pytest.fixture
def spatial_wcs_2d_small_angle():
    """
    This WCS has an almost linear correlation between the pixel and world axes
    close to the reference pixel.
    """
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ['HPLN-TAN', 'HPLT-TAN']
    wcs.wcs.crpix = [3.0] * 2
    wcs.wcs.cdelt = [0.002] * 2
    wcs.wcs.crval = [0] * 2
    wcs.wcs.set()
    return wcs


def test_local_pixel_derivatives(spatial_wcs_2d_small_angle):
    not_diag = np.logical_not(np.diag([1,1]))
    # At (or close to) the reference pixel this should equal the cdelt
    derivs = local_partial_pixel_derivatives(spatial_wcs_2d_small_angle, 3, 3)
    np.testing.assert_allclose(np.diag(derivs), spatial_wcs_2d_small_angle.wcs.cdelt)
    np.testing.assert_allclose(derivs[not_diag].flat, [0,0], atol=1e-10)

    # Far away from the reference pixel this should not equal the cdelt
    derivs = local_partial_pixel_derivatives(spatial_wcs_2d_small_angle, 3e4, 3e4)
    assert not np.allclose(np.diag(derivs), spatial_wcs_2d_small_angle.wcs.cdelt)

    # At (or close to) the reference pixel this should equal the cdelt
    derivs = local_partial_pixel_derivatives(spatial_wcs_2d_small_angle, 3, 3, normalize_by_world=True)
    np.testing.assert_allclose(np.diag(derivs), [1, 1])
    np.testing.assert_allclose(derivs[not_diag].flat, [0,0], atol=1e-8)


def test_pixel_to_world_correlation_matrix_celestial():

    wcs = WCS(naxis=2)
    wcs.wcs.ctype = 'RA---TAN', 'DEC--TAN'
    wcs.wcs.set()

    assert_equal(wcs.axis_correlation_matrix, [[1, 1], [1, 1]])
    matrix, classes = _pixel_to_world_correlation_matrix(wcs)
    assert_equal(matrix, [[1, 1]])
    assert classes == [SkyCoord]


def test_pixel_to_world_correlation_matrix_spectral_cube_uncorrelated():

    wcs = WCS(naxis=3)
    wcs.wcs.ctype = 'RA---TAN', 'FREQ', 'DEC--TAN'
    wcs.wcs.set()

    assert_equal(wcs.axis_correlation_matrix, [[1, 0, 1], [0, 1, 0], [1, 0, 1]])
    matrix, classes = _pixel_to_world_correlation_matrix(wcs)
    assert_equal(matrix, [[1, 0, 1], [0, 1, 0]])
    assert classes == [SkyCoord, Quantity]


def test_pixel_to_world_correlation_matrix_spectral_cube_correlated():

    wcs = WCS(naxis=3)
    wcs.wcs.ctype = 'RA---TAN', 'FREQ', 'DEC--TAN'
    wcs.wcs.cd = np.ones((3, 3))
    wcs.wcs.set()

    assert_equal(wcs.axis_correlation_matrix, [[1, 1, 1], [1, 1, 1], [1, 1, 1]])
    matrix, classes = _pixel_to_world_correlation_matrix(wcs)
    assert_equal(matrix, [[1, 1, 1], [1, 1, 1]])
    assert classes == [SkyCoord, Quantity]


def test_pixel_to_pixel_correlation_matrix_celestial():

    wcs_in = WCS(naxis=2)
    wcs_in.wcs.ctype = 'RA---TAN', 'DEC--TAN'
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=2)
    wcs_out.wcs.ctype = 'DEC--TAN', 'RA---TAN'
    wcs_out.wcs.set()

    matrix = _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out)
    assert_equal(matrix, [[1, 1], [1, 1]])


def test_pixel_to_pixel_correlation_matrix_spectral_cube_uncorrelated():

    wcs_in = WCS(naxis=3)
    wcs_in.wcs.ctype = 'RA---TAN', 'DEC--TAN', 'FREQ'
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=3)
    wcs_out.wcs.ctype = 'DEC--TAN', 'FREQ', 'RA---TAN'
    wcs_out.wcs.set()

    matrix = _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out)
    assert_equal(matrix, [[1, 1, 0], [0, 0, 1], [1, 1, 0]])


def test_pixel_to_pixel_correlation_matrix_spectral_cube_correlated():

    # NOTE: only make one of the WCSes have correlated axes to really test this

    wcs_in = WCS(naxis=3)
    wcs_in.wcs.ctype = 'RA---TAN', 'DEC--TAN', 'FREQ'
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=3)
    wcs_out.wcs.ctype = 'DEC--TAN', 'FREQ', 'RA---TAN'
    wcs_out.wcs.cd = np.ones((3, 3))
    wcs_out.wcs.set()

    matrix = _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out)
    assert_equal(matrix, [[1, 1, 1], [1, 1, 1], [1, 1, 1]])


def test_pixel_to_pixel_correlation_matrix_mismatch():

    wcs_in = WCS(naxis=2)
    wcs_in.wcs.ctype = 'RA---TAN', 'DEC--TAN'
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=3)
    wcs_out.wcs.ctype = 'DEC--TAN', 'FREQ', 'RA---TAN'
    wcs_out.wcs.set()

    with pytest.raises(ValueError) as exc:
        _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out)
    assert exc.value.args[0] == "The two WCS return a different number of world coordinates"

    wcs3 = WCS(naxis=2)
    wcs3.wcs.ctype = 'FREQ', 'PIXEL'
    wcs3.wcs.set()

    with pytest.raises(ValueError) as exc:
        _pixel_to_pixel_correlation_matrix(wcs_out, wcs3)
    assert exc.value.args[0] == "The world coordinate types of the two WCS do not match"

    wcs4 = WCS(naxis=4)
    wcs4.wcs.ctype = 'RA---TAN', 'DEC--TAN', 'Q1', 'Q2'
    wcs4.wcs.cunit = ['deg', 'deg', 'm/s', 'm/s']
    wcs4.wcs.set()

    wcs5 = WCS(naxis=4)
    wcs5.wcs.ctype = 'Q1', 'RA---TAN', 'DEC--TAN', 'Q2'
    wcs5.wcs.cunit = ['m/s', 'deg', 'deg', 'm/s']
    wcs5.wcs.set()

    with pytest.raises(ValueError) as exc:
        _pixel_to_pixel_correlation_matrix(wcs4, wcs5)
    assert exc.value.args[0] == "World coordinate order doesn't match and automatic matching is ambiguous"


def test_pixel_to_pixel_correlation_matrix_nonsquare():

    # Here we set up an input WCS that maps 3 pixel coordinates to 4 world
    # coordinates - the idea is to make sure that things work fine in cases
    # where the number of input and output pixel coordinates do not match.

    class FakeWCS(object):
        pass

    wcs_in = FakeWCS()
    wcs_in.low_level_wcs = wcs_in
    wcs_in.pixel_n_dim = 3
    wcs_in.world_n_dim = 4
    wcs_in.axis_correlation_matrix = [[True, True, False],
                                      [True, True, False],
                                      [True, True, False],
                                      [False, False, True]]
    wcs_in.world_axis_object_components = [('spat', 'ra', 'ra.degree'),
                                           ('spat', 'dec', 'dec.degree'),
                                           ('spec', 0, 'value'),
                                           ('time', 0, 'utc.value')]
    wcs_in.world_axis_object_classes = {'spat': ('astropy.coordinates.SkyCoord', (),
                                                 {'frame': 'icrs'}),
                                        'spec': ('astropy.units.Wavelength', (None,), {}),
                                        'time': ('astropy.time.Time', (None,),
                                                 {'format': 'mjd', 'scale': 'utc'})}

    wcs_out = FakeWCS()
    wcs_out.low_level_wcs = wcs_out
    wcs_out.pixel_n_dim = 4
    wcs_out.world_n_dim = 4
    wcs_out.axis_correlation_matrix = [[True, False, False, False],
                                       [False, True, True, False],
                                       [False, True, True, False],
                                       [False, False, False, True]]
    wcs_out.world_axis_object_components = [('spec', 0, 'value'),
                                            ('spat', 'ra', 'ra.degree'),
                                            ('spat', 'dec', 'dec.degree'),
                                            ('time', 0, 'utc.value')]
    wcs_out.world_axis_object_classes = wcs_in.world_axis_object_classes

    matrix = _pixel_to_pixel_correlation_matrix(wcs_in, wcs_out)

    matrix = matrix.astype(int)

    # The shape should be (n_pixel_out, n_pixel_in)
    assert matrix.shape == (4, 3)

    expected = np.array([[1, 1, 0], [1, 1, 0], [1, 1, 0], [0, 0, 1]])
    assert_equal(matrix, expected)


def test_split_matrix():

    assert _split_matrix(np.array([[1]])) == [([0], [0])]

    assert _split_matrix(np.array([[1, 1],
                                  [1, 1]])) == [([0, 1], [0, 1])]

    assert _split_matrix(np.array([[1, 1, 0],
                                  [1, 1, 0],
                                  [0, 0, 1]])) == [([0, 1], [0, 1]), ([2], [2])]

    assert _split_matrix(np.array([[0, 1, 0],
                                  [1, 0, 0],
                                  [0, 0, 1]])) == [([0], [1]), ([1], [0]), ([2], [2])]

    assert _split_matrix(np.array([[0, 1, 1],
                                  [1, 0, 0],
                                  [1, 0, 1]])) == [([0, 1, 2], [0, 1, 2])]


def test_pixel_to_pixel():

    wcs_in = WCS(naxis=3)
    wcs_in.wcs.ctype = 'DEC--TAN', 'FREQ', 'RA---TAN'
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=3)
    wcs_out.wcs.ctype = 'GLON-CAR', 'GLAT-CAR', 'FREQ'
    wcs_out.wcs.set()

    # First try with scalars
    x, y, z = pixel_to_pixel(wcs_in, wcs_out, 1, 2, 3)
    assert x.shape == ()
    assert y.shape == ()
    assert z.shape == ()

    # Now try with broadcasted arrays
    x = np.linspace(10, 20, 10)
    y = np.linspace(10, 20, 20)
    z = np.linspace(10, 20, 30)
    Z1, Y1, X1 = np.meshgrid(z, y, x, indexing='ij', copy=False)
    X2, Y2, Z2 = pixel_to_pixel(wcs_in, wcs_out, X1, Y1, Z1)

    # The final arrays should have the correct shape
    assert X2.shape == (30, 20, 10)
    assert Y2.shape == (30, 20, 10)
    assert Z2.shape == (30, 20, 10)

    # But behind the scenes should also be broadcasted
    assert unbroadcast(X2).shape == (30, 1, 10)
    assert unbroadcast(Y2).shape == (30, 1, 10)
    assert unbroadcast(Z2).shape == (20, 1)

    # We can put the values back through the function to ensure round-tripping
    X3, Y3, Z3 = pixel_to_pixel(wcs_out, wcs_in, X2, Y2, Z2)

    # The final arrays should have the correct shape
    assert X2.shape == (30, 20, 10)
    assert Y2.shape == (30, 20, 10)
    assert Z2.shape == (30, 20, 10)

    # But behind the scenes should also be broadcasted
    assert unbroadcast(X3).shape == (30, 1, 10)
    assert unbroadcast(Y3).shape == (20, 1)
    assert unbroadcast(Z3).shape == (30, 1, 10)

    # And these arrays should match the input
    assert_allclose(X1, X3)
    assert_allclose(Y1, Y3)
    assert_allclose(Z1, Z3)


def test_pixel_to_pixel_correlated():

    wcs_in = WCS(naxis=2)
    wcs_in.wcs.ctype = 'DEC--TAN', 'RA---TAN'
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=2)
    wcs_out.wcs.ctype = 'GLON-CAR', 'GLAT-CAR'
    wcs_out.wcs.set()

    # First try with scalars
    x, y = pixel_to_pixel(wcs_in, wcs_out, 1, 2)
    assert x.shape == ()
    assert y.shape == ()

    # Now try with broadcasted arrays
    x = np.linspace(10, 20, 10)
    y = np.linspace(10, 20, 20)
    Y1, X1 = np.meshgrid(y, x, indexing='ij', copy=False)
    Y2, X2 = pixel_to_pixel(wcs_in, wcs_out, X1, Y1)

    # The final arrays should have the correct shape
    assert X2.shape == (20, 10)
    assert Y2.shape == (20, 10)

    # and there are no efficiency gains here since the celestial axes are correlated
    assert unbroadcast(X2).shape == (20, 10)


def test_pixel_to_pixel_1d():

    # Simple test to make sure that when WCS only returns one world coordinate
    # this still works correctly (since this requires special treatment behind
    # the scenes).

    wcs_in = WCS(naxis=1)
    wcs_in.wcs.ctype = 'COORD1',
    wcs_in.wcs.cunit = 'nm',
    wcs_in.wcs.set()

    wcs_out = WCS(naxis=1)
    wcs_out.wcs.ctype = 'COORD2',
    wcs_out.wcs.cunit = 'cm',
    wcs_out.wcs.set()

    # First try with a scalar
    x = pixel_to_pixel(wcs_in, wcs_out, 1)
    assert x.shape == ()

    # Next with a regular array
    x = np.linspace(10, 20, 10)
    x = pixel_to_pixel(wcs_in, wcs_out, x)
    assert x.shape == (10,)

    # And now try with a broadcasted array
    x = np.broadcast_to(np.linspace(10, 20, 10), (4, 10))
    x = pixel_to_pixel(wcs_in, wcs_out, x)
    assert x.shape == (4, 10)

    # The broadcasting of the input should be retained
    assert unbroadcast(x).shape == (10,)

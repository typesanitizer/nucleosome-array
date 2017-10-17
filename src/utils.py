import numpy as np
from numba import jit

@jit(cache=True, nopython=True)
def rotation_matrices(euler):
    """Computes rotation matrices element-wise.

    Assumes: indices 0, 1 and 2 ↔ phi, theta, psi.
    """
    n = len(euler)
    R = np.empty((n, 3, 3))
    for i in range(n):
        phi = euler[i, 0]
        cos_phi = np.cos(phi)
        sin_phi = np.sin(phi)
        theta = euler[i, 1]
        cos_theta = np.cos(theta)
        sin_theta = np.sin(theta)
        psi = euler[i, 2]
        cos_psi = np.cos(psi)
        sin_psi = np.sin(psi)

        R[i, 0, 0] = cos_phi * cos_psi - cos_theta * sin_phi * sin_psi
        R[i, 0, 1] = cos_phi * sin_psi + cos_theta * cos_psi * sin_phi
        R[i, 0, 2] = sin_theta * sin_phi

        R[i, 1, 0] = -cos_psi * sin_phi - cos_theta * cos_phi * sin_psi
        R[i, 1, 1] = -sin_phi * sin_psi + cos_theta * cos_phi * cos_psi
        R[i, 1, 2] = cos_phi * sin_theta

        R[i, 2, 0] = sin_theta * sin_psi
        R[i, 2, 1] = -cos_psi * sin_theta
        R[i, 2, 2] = cos_theta
    return R

def partition(n_parts, total):
    arr = np.array([total // n_parts] * n_parts if total >= n_parts else [])
    rem = total % n_parts
    if rem != 0:
        return np.append(arr, rem)
    return arr

def smart_arange(start, stop, step, incl=True):
    s = step if (stop - start) * step > 0 else -step
    return np.arange(start, stop + (s if incl else 0.0), s)

def twist_steps(default_step_size, twists):
    try:
        f = np.float(twists)
        tmp = default_step_size if abs(default_step_size) <= abs(f) else f
        return smart_arange(0., f, tmp)
    except TypeError:
        if type(twists) is tuple:
            x = len(twists)
            if x == 2:
                return smart_arange(0., twists[0], twists[1])
            elif x == 3:
                return smart_arange(*twists)
            else:
                raise ValueError("The tuple must be of length 2 or 3.")
        else:
            return np.array(twists, dtype=float)

_r_0 = 4.18 # in nm, for central line of DNA wrapped around nucleosome
_z_0 = 2.39 # pitch of superhelix in nm
_n_wrap = 1.65 # number of times DNA winds around nucleosome
_zeta_max = 2.*np.pi*_n_wrap
_helix_entry_tilt = np.arctan2(-2.*np.pi*_r_0, _z_0)
# called lambda in the notes

def normalize(v):
    norm_v = np.linalg.norm(v)
    assert norm_v > 0.
    return v/norm_v

# Final normal, tangent and binormal vectors
_n_f = np.array([-np.cos(_zeta_max), np.sin(_zeta_max), 0.])
_t_f = normalize(np.array([
    -_r_0 * np.sin(_zeta_max),
    -_r_0 * np.cos(_zeta_max),
     _z_0 / (2.*np.pi)
]))
_b_f = np.cross(_t_f, _n_f)
_nf_tf_matrix = np.array([_n_f, _b_f, _t_f])

@jit(cache=True, nopython=True)
def axialRotMatrix(theta, axis=2):
    """Returns an Euler matrix for a passive rotation about a particular axis.

    `axis` should be 0 (x), 1 (y) or 2 (z).
    **Warning**: This function does not do input validation.
    """
    # Using tuples because nested lists don't work with array in Numba 0.35.0
    if axis == 2:
        rot = np.array((
            ( np.cos(theta), np.sin(theta), 0.),
            (-np.sin(theta), np.cos(theta), 0.),
            (            0.,            0., 1.)
        ))
    elif axis == 0:
        rot = np.array((
            (1.,             0.,            0.),
            (0.,  np.cos(theta), np.sin(theta)),
            (0., -np.sin(theta), np.cos(theta))
        ))
    else:
        rot = np.array((
            (np.cos(theta), 0., -np.sin(theta)),
            (           0., 1.,             0.),
            (np.sin(theta), 0.,  np.cos(theta))
        ))
    return rot

@jit(cache=True, nopython=True)
def anglesOfEulerMatrix(m):
    """Returns an array of angles in the order phi, theta, psi.

    This function is the inverse of eulerMatrixOfAngles.
    """
    # NOTE: order in arctan2 is opposite to that of Mathematica
    if m[2][2] == 1.0:
        l = np.array([0., 0., np.arctan2(m[0][1], m[0][0])])
    elif m[2][2] == -1.0:
        l = np.array([0., np.pi, np.arctan2(m[0][1], m[0][0])])
    else:
        l = np.array([
            np.arctan2(m[0][2], m[1][2]),
            np.arccos(m[2][2]),
            np.arctan2(m[2][0], -m[2][1])
        ])
    return l

@jit(cache=True, nopython=True)
def _multiplyMatrices3(m1, m2, m3):
    """Multiplies the given matrices from left to right."""
    # using np.dot as Numba 0.35.0 doesn't support np.matmul (@ operator).
    # See https://github.com/numba/numba/issues/2101
    return np.dot(np.dot(m1, m2), m3)

@jit(cache=True, nopython=True)
def eulerMatrixOfAngles(angles):
    """Returns the Euler matrix for passive rotations for the given angles.

    `angles` is a 1D array of length 3 with angles phi, theta and psi.
    This function is the inverse of anglesOfEulerMatrix
    """
    return _multiplyMatrices3(
        axialRotMatrix(angles[0], axis=2),
        axialRotMatrix(angles[1], axis=0),
        axialRotMatrix(angles[2], axis=2)
    )

@jit(cache=True, nopython=True)
def _AmatrixFromMatrix(entryMatrix):
    return _multiplyMatrices3(
        axialRotMatrix(_helix_entry_tilt, 0),
        axialRotMatrix(np.pi, 2),
        entryMatrix.transpose()
    )
    # TODO:
    # I don't understand why the last transpose is needed.
    # According to the Mathematica code, it shouldn't be needed.

@jit(cache=True, nopython=True)
def _AmatrixFromAngles(entryangles):
    # Numba 0.35.0 supports .transpose() but not np.transpose().
    return _AmatrixFromMatrix(eulerMatrixOfAngles(entryangles))

# angles given in order phi, theta, psi
@jit(cache=True, nopython=True)
def exitMatrix(entryangles):
    return (np.dot(_nf_tf_matrix, _AmatrixFromAngles(entryangles))).transpose()

@jit(cache=True, nopython=True)
def exitAngles(entryangles):
    return anglesOfEulerMatrix(exitMatrix(entryangles))

@jit(cache=True, nopython=True)
def calc_deltas(deltas, nucs, Rs):
    for i in nucs:
        deltas[i] = _multiplyMatrices3(_nf_tf_matrix, _AmatrixFromMatrix(Rs[i-1]), Rs[i])

@jit(cache=True, nopython=True)
def md_jacobian(tangent):
    n = len(tangent)
    J = np.empty((n, 4, 4))
    for i in range(n):
        t = tangent[i]
        D_sq = t[0]**2 + t[1]**2 + t[2]**2
        D = np.sqrt(D_sq)
        p_sq = t[0]**2 + t[1]**2 + 1.E-16
        p = np.sqrt(p_sq)

        J[i, 0, 0] = -t[0] / D
        J[i, 0, 1] = -t[1] / D
        J[i, 0, 2] = -t[2] / D
        J[i, 0, 3] = 0.

        J[i, 1, 0] = -t[1] / p_sq
        J[i, 1, 1] = +t[0] / p_sq
        J[i, 1, 2] = 0.
        J[i, 1, 3] = 0.

        J[i, 2, 0] = -t[0] * t[2] / (p * D_sq)
        J[i, 2, 1] = -t[1] * t[2] / (p * D_sq)
        J[i, 2, 2] = p / D_sq
        J[i, 2, 3] = 0.

        J[i, 3, 0] = 0.
        J[i, 3, 1] = 0.
        J[i, 3, 2] = 0.
        J[i, 3, 3] = 0.
    return J

@jit(cache=True, nopython=True)
def md_derivative_rotation_matrices(euler):
    n = len(euler)
    DR = np.empty((n, 3, 3, 3))
    for i in range(n):
        phi = euler[i, 0]
        cos_phi = np.cos(phi)
        sin_phi = np.sin(phi)
        theta = euler[i, 1]
        cos_theta = np.cos(theta)
        sin_theta = np.sin(theta)
        psi = euler[i, 2]
        cos_psi = np.cos(psi)
        sin_psi = np.sin(psi)

        DR[i, 0, 0, 0] = -sin_phi * cos_psi - cos_phi * cos_theta * sin_psi
        DR[i, 0, 0, 1] = sin_phi * sin_theta * sin_psi
        DR[i, 0, 0, 2] = -sin_phi * cos_theta * cos_psi - cos_phi * sin_psi

        DR[i, 0, 1, 0] = cos_phi * cos_theta * cos_psi - sin_phi * sin_psi
        DR[i, 0, 1, 1] = -sin_phi * sin_theta * cos_psi
        DR[i, 0, 1, 2] = cos_phi * cos_psi - sin_phi * cos_theta * sin_psi

        DR[i, 0, 2, 0] = cos_phi * sin_theta
        DR[i, 0, 2, 1] = sin_phi * cos_theta
        DR[i, 0, 2, 2] = 0.

        DR[i, 1, 0, 0] = -cos_phi * cos_psi + sin_phi * cos_theta * sin_psi
        DR[i, 1, 0, 1] = cos_phi * sin_theta * sin_psi
        DR[i, 1, 0, 2] = -cos_phi * cos_theta * cos_psi + sin_phi * sin_psi

        DR[i, 1, 1, 0] = -sin_phi * cos_theta * cos_psi - cos_phi * sin_psi
        DR[i, 1, 1, 1] = -cos_phi * sin_theta * cos_psi
        DR[i, 1, 1, 2] = -sin_phi * cos_psi - cos_phi * cos_theta * sin_psi

        DR[i, 1, 2, 0] = -sin_phi * sin_theta
        DR[i, 1, 2, 1] = cos_phi * cos_theta
        DR[i, 1, 2, 2] = 0.

        DR[i, 2, 0, 0] = 0.
        DR[i, 2, 0, 1] = cos_theta * sin_psi
        DR[i, 2, 0, 2] = sin_theta * cos_psi

        DR[i, 2, 1, 0] = 0.
        DR[i, 2, 1, 1] = -cos_theta * cos_psi
        DR[i, 2, 1, 2] = sin_theta * sin_psi

        DR[i, 2, 2, 0] = 0.
        DR[i, 2, 2, 1] = -sin_theta
        DR[i, 2, 2, 2] = 0.
    return DR

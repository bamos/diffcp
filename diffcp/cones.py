import numpy as np
import scipy.sparse as sparse
import scipy.sparse.linalg as splinalg
import warnings

from _diffcp import dprojection, project_exp_cone, Cone, ConeType

ZERO = "f"
POS = "l"
SOC = "q"
PSD = "s"
EXP = "ep"
EXP_DUAL = "ed"
POWER = "p"

# The ordering of CONES matches SCS.
CONES = [ZERO, POS, SOC, PSD, EXP, EXP_DUAL, POWER]

# Map from Python cones to CPP format
CONE_MAP = {
    "f": ConeType.ZERO,
    "l": ConeType.POS,
    "q": ConeType.SOC,
    "s": ConeType.PSD,
    "ep": ConeType.EXP
}


def parse_cone_dict_cpp(cone_list):
    return [Cone(CONE_MAP[cone], [l] if not isinstance(l, (list, tuple)) else l)
            for cone, l in cone_list]


def parse_cone_dict(cone_dict):
    """Parses SCS-style cone dictionary."""
    return [(cone, cone_dict[cone]) for cone in CONES if cone in cone_dict]


def as_block_diag_linear_operator(matrices):
    """Block diag of SciPy sparse matrices (or linear operators)."""
    linear_operators = [splinalg.aslinearoperator(
        op) if not isinstance(op, splinalg.LinearOperator) else op
        for op in matrices]
    num_operators = len(linear_operators)
    nrows = [op.shape[0] for op in linear_operators]
    ncols = [op.shape[1] for op in linear_operators]
    m, n = sum(nrows), sum(ncols)
    row_indices = np.append(0, np.cumsum(nrows))
    col_indices = np.append(0, np.cumsum(ncols))

    def matvec(x):
        output = np.zeros(m)
        for i, op in enumerate(linear_operators):
            z = x[col_indices[i]:col_indices[i + 1]].ravel()
            output[row_indices[i]:row_indices[i + 1]] = op.matvec(z)
        return output

    def rmatvec(y):
        output = np.zeros(n)
        for i, op in enumerate(linear_operators):
            z = y[row_indices[i]:row_indices[i + 1]].ravel()
            output[col_indices[i]:col_indices[i + 1]] = op.rmatvec(z)
        return output

    return splinalg.LinearOperator((m, n), matvec=matvec, rmatvec=rmatvec)



def vec_psd_dim(dim):
    return int(dim * (dim + 1) / 2)


def psd_dim(size):
    return int(np.sqrt(2 * size))


def unvec_symm(x, dim):
    """Returns a dim-by-dim symmetric matrix corresponding to `x`.

    `x` is a vector of length dim*(dim + 1)/2, corresponding to a symmetric
    matrix; the correspondence is as in SCS.
    X = [ X11 X12 ... X1k
          X21 X22 ... X2k
          ...
          Xk1 Xk2 ... Xkk ],
    where
    vec(X) = (X11, sqrt(2)*X21, ..., sqrt(2)*Xk1, X22, sqrt(2)*X32, ..., Xkk)
    """
    X = np.zeros((dim, dim))
    # triu_indices gets indices of upper triangular matrix in row-major order
    col_idx, row_idx = np.triu_indices(dim)
    X[(row_idx, col_idx)] = x
    X = X + X.T
    X /= np.sqrt(2)
    X[np.diag_indices(dim)] = np.diagonal(X) * np.sqrt(2) / 2
    return X


def vec_symm(X):
    """Returns a vectorized representation of a symmetric matrix `X`.

    Vectorization (including scaling) as per SCS.
    vec(X) = (X11, sqrt(2)*X21, ..., sqrt(2)*Xk1, X22, sqrt(2)*X32, ..., Xkk)
    """
    X = X.copy()
    X *= np.sqrt(2)
    X[np.diag_indices(X.shape[0])] = np.diagonal(X) / np.sqrt(2)
    col_idx, row_idx = np.triu_indices(X.shape[0])
    return X[(row_idx, col_idx)]


def _proj(x, cone, dual=False):
    """Returns the projection of x onto a cone or its dual cone."""
    if cone == ZERO:
        return x if dual else np.zeros(x.shape)
    elif cone == POS:
        return np.maximum(x, 0)
    elif cone == SOC:
        t = x[0]
        z = x[1:]
        norm_z = np.linalg.norm(z, 2)
        if norm_z <= t or np.isclose(norm_z, t, atol=1e-8):
            return x
        elif norm_z <= -t:
            return np.zeros(x.shape)
        else:
            return 0.5 * (1 + t / norm_z) * np.append(norm_z, z)
    elif cone == PSD:
        dim = psd_dim(x.size)
        X = unvec_symm(x, dim)
        lambd, Q = np.linalg.eig(X)
        return vec_symm(Q @ sparse.diags(np.maximum(lambd, 0)) @ Q.T)
    elif cone == EXP:
        num_cones = int(x.size / 3)
        out = np.zeros(x.size)
        offset = 0
        for _ in range(num_cones):
            x_i = x[offset:offset + 3]
            if dual:
                x_i = x_i * -1
            out[offset:offset + 3] = project_exp_cone(x_i);
            offset += 3
        # via Moreau: Pi_K*(x) = x + Pi_K(-x)
        return x + out if dual else out
    else:
        raise NotImplementedError(f"{cone} not implemented")


def _dproj_explicit(x, cone, dual=False):
    shape = (x.size, x.size)
    if cone == ZERO:
        return sparse.eye(*shape) if dual else sparse.csc_matrix(shape)
    elif cone == POS:
        return sparse.diags(.5 * (np.sign(x) + 1), format="csc")
    elif cone == SOC:
        t = x[0]
        z = x[1:]
        norm_z = np.linalg.norm(z, 2)
        if norm_z <= t:
            return sparse.eye(*shape)
        elif norm_z <= -t:
            return sparse.csc_matrix(shape)
        else:
            # z = z.reshape(z.size)
            unit_z = z / norm_z
            scale_factor = 1.0 / (2 * norm_z)
            t_plus_norm_z = t + norm_z

            return scale_factor * np.bmat([
                [np.array([[norm_z]]), z[np.newaxis, :]],
                [z[:, np.newaxis], t_plus_norm_z *
                    np.eye(z.size) - t * np.outer(unit_z, unit_z)]
            ])
    elif cone == EXP:
        DP = _dproj(x, cone, dual=dual)
        return DP @ np.eye(DP.shape[0])
    else:
        raise NotImplementedError(f"{cone} not implemented")

def pi(x, cones, dual=False):
    """Projects x onto product of cones (or their duals)

    Args:
        x: NumPy array (with PSD data formatted in SCS convention)
        cones: list of (cone name, size)
        dual: whether to project onto the dual cone

    Returns:
        NumPy array that is the projection of `x` onto the (dual) cones
    """
    projection = np.zeros(x.shape)
    offset = 0
    for cone, sz in cones:
        sz = sz if isinstance(sz, (tuple, list)) else (sz,)
        if sum(sz) == 0:
            continue
        for dim in sz:
            if cone == PSD:
                dim = vec_psd_dim(dim)
            elif cone == EXP:
                dim *= 3
            projection[offset:offset + dim] = _proj(
                x[offset:offset + dim], cone, dual=dual)
            offset += dim
    return projection


def dpi_explicit(x, cones, dual=False):
    """Derivative of projection onto product of cones (or their duals), at x

    Args:
        x: NumPy array
        cones: list of (cone name, size)
        dual: whether to project onto the dual cone

    Returns:
        An abstract linear map representing the derivative, with methods
        `matvec` and `rmatvec`
    """
    dprojections = []
    offset = 0
    for cone, sz in cones:
        sz = sz if isinstance(sz, (tuple, list)) else (sz,)
        if sum(sz) == 0:
            continue
        for dim in sz:
            if cone == PSD:
                dim = vec_psd_dim(dim)
            elif cone == EXP:
                dim *= 3
            dprojections.append(
                _dproj_explicit(x[offset:offset + dim], cone, dual=dual))
            offset += dim
    return sparse.block_diag(dprojections)

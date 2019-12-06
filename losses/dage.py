import tensorflow as tf
K = tf.compat.v2.keras.backend
from utils.dataset_gen import DTYPE
from enum import Enum
from functools import partial

# Configuration parameters
class ConnectionType(Enum):
    ALL                 = 'ALL'
    SOURCE_TARGET       = 'SOURCE_TARGET'
    SOURCE_TARGET_PAIR  = 'SOURCE_TARGET_PAIR'

class FilterType(Enum):
    ALL     = 'ALL'
    KNN     = 'KNN'
    KFN     = 'KFN'
    EPSILON = 'EPSILON'

class WeightType(Enum):
    INDICATOR   = 'INDICATOR'
    GAUSSIAN    = 'GAUSSIAN'

def string2weight_type(s):
    return 

# Util
def counter():
    c = 0
    while True:
        c += 1
        yield c
zeros_count = counter()
ones_count = counter()

# We need to wrap the zeros and ones function because unique names are mandatory in the graph
def zeros(shape, dtype=tf.bool):
    name = 'zeros_{}'.format(next(zeros_count))
    return tf.zeros(shape, dtype, name)

def ones(shape, dtype=tf.bool):
    name = 'ones_{}'.format(next(ones_count))
    return tf.ones(shape, dtype, name)

def str2enum(s, E):
    if isinstance(s, str):
        return E[s.upper()]
    elif isinstance(s, E):
        return s
    else:
        raise ValueError('{} should be either be {} or {}'.format(s, str, E))

def get_filt_dists(W_Wp, xs, xt):
    # Seing as the distances are also calculated within the fisher ratio of the embedding loss, there might be a performance optimisation to be made here
    W, Wp = W_Wp

    batch_size, embed_size = tf.shape(xs)[0], tf.shape(xs)[1]
    N = 2*batch_size 
    x = tf.concat([xs, xt], axis = 0) 

    xTe = tf.broadcast_to(tf.expand_dims(x, axis=1), shape=(N, N, embed_size))
    eTx = tf.broadcast_to(tf.expand_dims(x, axis=0), shape=(N, N, embed_size))

    dists = tf.reduce_sum(tf.square(xTe - eTx), axis=2)
    z = zeros([N,N], dtype=DTYPE)

    W_dists = tf.where(W, dists, z)
    Wp_dists = tf.where(Wp, dists, z)

    return W_dists, Wp_dists


def filt_k_max(x, k):
    k = tf.constant(k, dtype=tf.int32)
    N = tf.shape(x)[0]
    vals, inds = tf.nn.top_k(x, k=k)
    inds = tf.where(tf.greater(vals, tf.zeros_like(vals, dtype=DTYPE)), inds, -tf.ones_like(inds))
    inds = tf.sparse.to_indicator(
        sp_input=tf.sparse.from_dense(inds+1),
        vocab_size=N+1
    )[:,1:]
    return tf.where(inds, x, tf.zeros_like(x, dtype=DTYPE))


def filt_k_min(x, k):
    k = tf.constant(k, dtype=tf.int32)
    N = tf.shape(x)[0]
    very_neg = tf.multiply(tf.constant(DTYPE.max, dtype=DTYPE), tf.ones_like(x, dtype=DTYPE))
    neg_x = -tf.where(tf.equal(x, tf.zeros_like(x, dtype=DTYPE)), very_neg, x)
    vals, inds = tf.nn.top_k(neg_x, k=k)
    inds = tf.where(tf.less(vals, tf.zeros_like(vals, dtype=DTYPE)), inds, -tf.ones_like(inds))
    inds = tf.sparse.to_indicator(
        sp_input=tf.sparse.from_dense(inds+1),
        vocab_size=N+1
    )[:,1:]
    return tf.where(inds, x, tf.zeros_like(x, dtype=DTYPE))


def filt_epsilon(x, eps):
    eps = tf.multiply(tf.constant(eps, dtype=DTYPE), tf.ones_like(x, dtype=DTYPE))
    return tf.where(tf.less(x, eps), x, tf.zeros_like(x, dtype=DTYPE)) 


# Weight types
def dist2indicator(x):
    I = tf.ones_like(x, dtype=DTYPE)
    O = tf.zeros_like(x, dtype=DTYPE)
    return tf.where(tf.greater(x, O), I, O)


def dist2gaussian(x):
    gaussian = tf.exp(-x)
    O = tf.zeros_like(x, dtype=DTYPE)
    return tf.where(tf.equal(x, O), O, gaussian)


# FilterType
def filter_all(W_Wp, xs=None, xt=None):
    return W_Wp


def make_filter(
    filter_type:FilterType, 
    penalty_filter_type:FilterType, 
    filter_param:int, 
    penalty_filter_param:int
):
    filt_dict = {
        FilterType.ALL      : lambda x, p: x,
        FilterType.KNN      : filt_k_max,
        FilterType.KFN      : filt_k_min,
        FilterType.EPSILON  : filt_epsilon,
    }
    filt_fn = filt_dict[filter_type]
    p_filt_fn = filt_dict[penalty_filter_type]

    def fn(W_Wp, xs, xt):
        dists, p_dists = get_filt_dists(W_Wp, xs, xt)
        dists = filt_fn(dists, filter_param)
        p_dists = p_filt_fn(p_dists, penalty_filter_param)
        return dists, p_dists

    return fn


# ConnectionTypes
def connect_all(ys, yt, batch_size):
    N = 2*batch_size 
    y = tf.concat([ys, yt], axis = 0) 
    yTe = tf.broadcast_to(tf.expand_dims(y, axis=1), shape=(N, N))
    eTy = tf.broadcast_to(tf.expand_dims(y, axis=0), shape=(N, N))

    W = tf.equal(yTe, eTy)
    Wp = tf.not_equal(yTe, eTy)

    return W, Wp


def connect_source_target(ys, yt, batch_size):
    W_all, Wp_all = connect_all(ys, yt, batch_size)

    N = 2*batch_size 
    tile_size = [batch_size, batch_size]
    O = zeros(tile_size, dtype=tf.bool)
    I = ones(tile_size, dtype=tf.bool)
    ind = tf.concat([ tf.concat([O, I], axis=0),
                      tf.concat([I, O], axis=0) ], axis=1 )

    O = zeros([N,N], dtype=tf.bool)
    W = tf.where(ind, W_all, O)
    Wp = tf.where(ind, Wp_all, O)

    return W, Wp


def connect_source_target_pair(ys, yt, batch_size):
    eq = tf.linalg.diag(tf.equal(ys, yt))
    neq = tf.linalg.diag(tf.not_equal(ys, yt))
    O = zeros([batch_size, batch_size],dtype=tf.bool)
    W = tf.concat([tf.concat([O, eq], axis=0),
                   tf.concat([eq, O], axis=0)], axis=1)
    Wp = tf.concat([tf.concat([O, neq], axis=0),
                    tf.concat([neq, O], axis=0)], axis=1)
    return W, Wp


# Loss maker
def dage_loss(
    connection_type: ConnectionType, 
    weight_type: WeightType,
    filter_type: FilterType, 
    penalty_filter_type: FilterType, 
    filter_param=1,
    penalty_filter_param=1
): 
    connection_type     = str2enum(connection_type, ConnectionType)
    weight_type         = str2enum(weight_type, WeightType)
    filter_type         = str2enum(filter_type, FilterType)
    penalty_filter_type = str2enum(penalty_filter_type, FilterType)

    connect = {
        ConnectionType.ALL                : connect_all,
        ConnectionType.SOURCE_TARGET      : connect_source_target,
        ConnectionType.SOURCE_TARGET_PAIR : connect_source_target_pair,
    }[connection_type]

    transform = {
        WeightType.INDICATOR    : lambda W_Wp: (dist2indicator(W_Wp[0]), dist2indicator(W_Wp[1])),
        WeightType.GAUSSIAN     : lambda W_Wp: (dist2gaussian(W_Wp[0]), dist2gaussian(W_Wp[1])),
    }[weight_type]

    filt = make_filter(filter_type, penalty_filter_type, filter_param, penalty_filter_param)

    if filter_type==FilterType.ALL and penalty_filter_type==FilterType.ALL and weight_type==WeightType.INDICATOR:
        # performance optimisation
        def make_weights(xs, xt, ys, yt, batch_size):
            W, Wp = connect(ys, yt, batch_size)
            return tf.cast(W, dtype=DTYPE), tf.cast(Wp, dtype=DTYPE)
    else:
        def make_weights(xs, xt, ys, yt, batch_size):
            W, Wp = transform(filt( W_Wp=connect(ys, yt, batch_size),
                                    xs=xs,
                                    xt=xt ))
            return tf.cast(W, dtype=DTYPE), tf.cast(Wp, dtype=DTYPE)

    def loss_fn(y_true, y_pred):  
        ys = tf.argmax(tf.cast(y_true[:,0], dtype=tf.int32), axis=1)
        yt = tf.argmax(tf.cast(y_true[:,1], dtype=tf.int32), axis=1)
        xs = y_pred[:,0]
        xt = y_pred[:,1]
        θϕ = tf.transpose(tf.concat([xs,xt], axis=0))

        batch_size = tf.shape(ys)[0]

        # construct Weight matrix
        W, Wp = make_weights(xs, xt, ys, yt, batch_size)

        # construct Degree matrix
        D  = tf.linalg.diag(tf.reduce_sum(W,  axis=1)) 
        Dp = tf.linalg.diag(tf.reduce_sum(Wp, axis=1))

        # construct Graph Laplacian
        L  = tf.subtract(D, W)
        Lp = tf.subtract(Dp, Wp)
        
        # construct loss
        θϕLϕθ  = tf.matmul(θϕ, tf.matmul(L,  θϕ, transpose_b=True))
        θϕLpϕθ = tf.matmul(θϕ, tf.matmul(Lp, θϕ, transpose_b=True))

        loss = tf.linalg.trace(θϕLϕθ) / tf.linalg.trace(θϕLpϕθ)

        return loss

    return loss_fn


def dage_attention_loss(
    connection_type: ConnectionType, 
    weight_type: WeightType,
    filter_type: FilterType, 
    penalty_filter_type: FilterType, 
    filter_param=1,
    penalty_filter_param=1
): 
    # connection_type     = str2enum(connection_type, ConnectionType)
    # weight_type         = str2enum(weight_type, WeightType)
    # filter_type         = str2enum(filter_type, FilterType)
    # penalty_filter_type = str2enum(penalty_filter_type, FilterType)

    # connect = {
    #     ConnectionType.ALL                : connect_all,
    #     ConnectionType.SOURCE_TARGET      : connect_source_target,
    #     ConnectionType.SOURCE_TARGET_PAIR : connect_source_target_pair,
    # }[connection_type]

    # transform = {
    #     WeightType.INDICATOR : lambda W_Wp: (dist2indicator(W_Wp[0]), dist2indicator(W_Wp[1])),
    #     WeightType.GAUSSIAN  : lambda W_Wp: (dist2gaussian(W_Wp[0]), dist2gaussian(W_Wp[1])),
    # }[weight_type]

    # filt = make_filter(filter_type, penalty_filter_type, filter_param, penalty_filter_param)

    # if filter_type==FilterType.ALL and penalty_filter_type==FilterType.ALL and weight_type==WeightType.INDICATOR:
    #     # performance optimisation
    #     def make_weights(xs, xt, ys, yt, batch_size):
    #         W, Wp = connect(ys, yt, batch_size)
    #         return tf.cast(W, dtype=DTYPE), tf.cast(Wp, dtype=DTYPE)
    # else:
    #     def make_weights(xs, xt, ys, yt, batch_size):
    #         W, Wp = transform(filt( W_Wp=connect(ys, yt, batch_size),
    #                                 xs=xs,
    #                                 xt=xt ))
    #         return tf.cast(W, dtype=DTYPE), tf.cast(Wp, dtype=DTYPE)


    def loss_fn(lbl_src, lbl_tgt, xs, xt, A, Ap):
        # ys = tf.argmax(tf.cast(lbl_src, dtype=tf.int32), axis=1)
        # yt = tf.argmax(tf.cast(lbl_tgt, dtype=tf.int32), axis=1)
        θϕ = tf.transpose(tf.concat([xs,xt], axis=0))

        # batch_size = tf.shape(xs)[0]

        # construct loss for bad attention
        # W, Wp = make_weights(xs, xt, ys, yt, batch_size)

        # construct Weight matrix
        W = A #tf.multiply(W, A)
        Wp = Ap #tf.multiply(Wp, Ap)

        # construct Degree matrix
        D  = tf.linalg.diag(tf.reduce_sum(W,  axis=1)) 
        Dp = tf.linalg.diag(tf.reduce_sum(Wp, axis=1))

        # construct Graph Laplacian
        L  = tf.subtract(D, W)
        Lp = tf.subtract(Dp, Wp)
        
        # construct loss
        θϕLϕθ  = tf.matmul(θϕ, tf.matmul(L,  θϕ, transpose_b=True))
        θϕLpϕθ = tf.matmul(θϕ, tf.matmul(Lp, θϕ, transpose_b=True))

        loss = tf.linalg.trace(θϕLϕθ) / tf.linalg.trace(θϕLpϕθ)

        return loss
    return loss_fn


# Predefined configurations
# dage_full_loss = dage_loss(
#     connection_type=ConnectionType.ALL, 
#     weight_type=WeightType.INDICATOR,
#     filter_type=FilterType.ALL,
#     penalty_filter_type=FilterType.ALL,
# )

# dage_full_across_loss = dage_loss(
#     connection_type=ConnectionType.SOURCE_TARGET, 
#     weight_type=WeightType.INDICATOR,
#     filter_type=FilterType.ALL,
#     penalty_filter_type=FilterType.ALL,
# )

# dage_pair_across_loss = dage_loss(
#     connection_type=ConnectionType.SOURCE_TARGET_PAIR, 
#     weight_type=WeightType.INDICATOR,
#     filter_type=FilterType.ALL,
#     penalty_filter_type=FilterType.ALL,
# )

# dage_ccsa_like_loss = dage_loss(
#     connection_type=ConnectionType.SOURCE_TARGET_PAIR, 
#     weight_type=WeightType.INDICATOR,
#     filter_type=FilterType.ALL,
#     penalty_filter_type=FilterType.EPSILON,
#     penalty_filter_param=1
# )

# dage_dsne_like_loss = dage_loss(
#     connection_type=ConnectionType.SOURCE_TARGET, 
#     weight_type=WeightType.INDICATOR,
#     filter_type=FilterType.KFN,
#     penalty_filter_type=FilterType.KNN,
#     filter_param=1,
#     penalty_filter_param=1
# )
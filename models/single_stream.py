import tensorflow as tf
keras = tf.compat.v2.keras
from math import ceil
from models.common import freeze, get_output_shape, model_dense, model_preds

def model(
    model_base, 
    input_shape, #currently unused
    output_shape,
    optimizer,
    freeze_base=True,
    embed_size=128,
    dense_size=1024
):
    if freeze_base:
        freeze(model_base)
    else:
        freeze(model_base, num_leave_unfrozen=4)

    model_mid = model_dense(input_shape=get_output_shape(model_base), dense_size=dense_size, embed_size=embed_size)
    model_top = model_preds(input_shape=get_output_shape(model_mid), output_shape=output_shape)

    model = keras.Sequential([ model_base, model_mid, model_top ])

    model.compile(
        loss=keras.losses.categorical_crossentropy, 
        loss_weights=None, 
        optimizer=optimizer, 
        metrics=['accuracy'],
    )

    return model


def train(
    model, 
    datasource, 
    datasource_size, 
    epochs, 
    batch_size, 
    callbacks, 
    verbose=1, 
    val_datasource=None, 
    val_datasource_size=None 
):
    validation_steps = ceil(val_datasource_size/batch_size) if val_datasource_size else None
    steps_per_epoch = ceil(datasource_size/batch_size)

    if not val_datasource_size:
        val_datasource = None
        validation_steps = None

    model.fit( 
        x=datasource, 
        validation_data=val_datasource,
        epochs=epochs, 
        steps_per_epoch=steps_per_epoch, 
        validation_steps=validation_steps,
        callbacks=callbacks,
        verbose=verbose,
    )
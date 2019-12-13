#!/usr/bin/env bash
DESCRIPTION="CCSA using gradual unfreeze. 
We repeat the test for multiple weightings of the aux loss vs the cross-entropy losses.
The weights from source tuning are used as a starting point. 
We perform the gradual unfreeze mechanism within this script, first training only new layers until convergence.
We then reduce the learing rate, and perform training again, with some base-layers unfrozen, this time using the weights from the previous iteration as starting point.
This is repeated, each time unfreezing more layers."

METHOD=ccsa
GPU_ID=2
OPTIMIZER=adam
ARCHITECTURE=two_stream_pair_embeds
MODEL_BASE=vgg16
FEATURES=images
BATCH_SIZE=12
AUGMENT=1
EXPERIMENT_ID_BASE="${MODEL_BASE}_alpha_search"
MODE="train_test_validate"

for ALPHA in 0.9 #0.25 0.5 
do
    for SEED in 0 1 2 3 4
    do
        for SOURCE in A W D
        do
            for TARGET in D A W
            do
                if [ $SOURCE != $TARGET ]
                then
                    FE_RUN_DIR="./runs/tune_source/${MODEL_BASE}_aug_ft_best/${SOURCE}${TARGET}"
                    FROM_WEIGHTS="${FE_RUN_DIR}/checkpoints/cp-best.ckpt"

                    EXPERIMENT_ID="${EXPERIMENT_ID_BASE}"
                    DIR_NAME=./runs/$METHOD/$EXPERIMENT_ID
                    mkdir $DIR_NAME -p
                    echo $DESCRIPTION > $DIR_NAME/description.txt

                    TIMESTAMP_OLD=$(date '+%Y%m%d%H%M%S')

                    python3 run.py \
                        --num_unfrozen_base_layers 0 \
                        --training_regimen  regular \
                        --timestamp         $TIMESTAMP_OLD \
                        --learning_rate     1e-5 \
                        --epochs            15 \
                        --gpu_id            $GPU_ID \
                        --optimizer         $OPTIMIZER \
                        --experiment_id     $EXPERIMENT_ID \
                        --source            $SOURCE \
                        --target            $TARGET \
                        --seed              $SEED \
                        --method            $METHOD \
                        --architecture      $ARCHITECTURE \
                        --model_base        $MODEL_BASE \
                        --features          $FEATURES \
                        --batch_size        $BATCH_SIZE \
                        --augment           $AUGMENT \
                        --from_weights      $FROM_WEIGHTS \
                        --loss_alpha        $ALPHA \
                        --mode              $MODE \

                    FROM_WEIGHTS="./runs/$METHOD/$EXPERIMENT_ID/${SOURCE}${TARGET}_${SEED}_${TIMESTAMP_OLD}/checkpoints/cp-best.ckpt"

                    EXPERIMENT_ID="${EXPERIMENT_ID_BASE}_coarse_grad_ft"
                    DIR_NAME=./runs/$METHOD/$EXPERIMENT_ID
                    mkdir $DIR_NAME -p
                    echo $DESCRIPTION > $DIR_NAME/description.txt

                    TIMESTAMP=$(date '+%Y%m%d%H%M%S')

                    python3 run.py \
                        --training_regimen  gradual_unfreeze \
                        --learning_rate     1e-5 \
                        --epochs            10 \
                        --optimizer         $OPTIMIZER \
                        --gpu_id            $GPU_ID \
                        --experiment_id     $EXPERIMENT_ID \
                        --source            $SOURCE \
                        --target            $TARGET \
                        --seed              $SEED \
                        --method            $METHOD \
                        --architecture      $ARCHITECTURE \
                        --model_base        $MODEL_BASE \
                        --features          $FEATURES \
                        --batch_size        $BATCH_SIZE \
                        --augment           $AUGMENT \
                        --from_weights      $FROM_WEIGHTS \
                        --loss_alpha        $ALPHA \
                        --mode              $MODE \
                        --timestamp         $TIMESTAMP \

                    # delete checkpoint
                    FT_RUN_DIR=./runs/$METHOD/$EXPERIMENT_ID/${SOURCE}${TARGET}_${SEED}_${TIMESTAMP}

                    if [ ! -f "$FT_RUN_DIR/report.json" ]; then
                        rm -rf $FT_RUN_DIR
                    else
                        rm -rf $FT_RUN_DIR/checkpoints
                        rm -rf $FE_RUN_DIR/checkpoints
                    fi
                fi
            done
        done
    done
done

./scripts/notify.sh "Finished job: ${METHOD}/${EXPERIMENT_ID_BASE} on GPU ${GPU_ID}."
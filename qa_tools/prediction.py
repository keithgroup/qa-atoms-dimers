# MIT License
# 
# Copyright (c) 2021, Alex M. Maldonado
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import numpy as np
import pandas as pd

from qa_tools.utils import *

def qa_predictions(
    df_qc, ref_label, ref_charge, excitation_level=0, lambda_values=[-1, 0, 1],
    basis_set='aug-cc-pV5Z', bond_length=None, ignore_one_row=True):
    """Quantum alchemy predictions of a reference system at specified lambda
    values.

    Parameters
    ----------
    df_qc : :obj:`pandas.dataframe`
        A dataframe with quantum chemistry data.
    ref_label : :obj:`str`
        The system label of the desired quantum alchemy reference system.
        For example, `'c'`, `'h'`, etc.
    ref_charge : :obj:`int`
        Total system charge of the quantum alchemy reference system.
    excitation_level : :obj:`int`, optional
        Electronic state of the system with respect to the ground state. ``0``
        represents the ground state, ``1`` the first excited state, etc.
        Defaults to ground state.
    lambda_values : :obj:`float`, :obj:`list`, optional
       Desired nuclear charge perturbations of the quantum alchemy reference
       system.
    basis_set : :obj:`str`, optional
        Desired basis sets the predictions are from. Defaults to
        ``aug-cc-pV5Z``.
    bond_length : :obj:`float`, optional
        Desired bond length for dimers; must be specified.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    
    Returns
    -------
    :obj:`numpy.ndarray`
        Energies at specified lambda values predicted using quantum alchemy.
    """
    if len(df_qc.iloc[0]['atomic_numbers']) == 2:
        df_qc = df_qc.query('bond_length == @bond_length')
    
    if not isinstance(lambda_values, np.ndarray) and not isinstance(lambda_values, list):
        lambda_values = np.array([lambda_values])
    
    ref_qc = df_qc.query(
        'system == @ref_label'
        '& charge == @ref_charge'
        '& basis_set == @basis_set'
        '& lambda_value in @lambda_values'
    )
    
    # Selects state if required.
    if len(set(df_qc['multiplicity'].values)) > 1:
        assert excitation_level is not None
        sys_mult = get_multiplicity(
            ref_qc, excitation_level, ignore_one_row=ignore_one_row
        )
        ref_qc = ref_qc.query('multiplicity == @sys_mult')

    energies = np.zeros(len(lambda_values))
    for i in range(len(lambda_values)):
        lambda_value = lambda_values[i]
        energies[i] = ref_qc.query(
            'lambda_value == @lambda_value'
        )['electronic_energy'].values[0]

    return energies

def qats_prediction(poly_coeffs, order, lambda_values):
    """Quantum alchemy predictions using a nth-order Taylor series.

    Parameters
    ----------
    poly_coeffs : :obj:`numpy.ndarray`
        Polynomial coefficients in increasing order (e.g., zeroth, first,
        second, etc.).
    order :obj:`int`
        Highest order to include in the Taylor series.
    lambda_values : :obj:`float`, :obj:`list`
        Lambda values to make QATS predictions of.
    
    Returns
    -------
    :obj:`numpy.ndarray`
        QATS predictions using a nth-order Taylor series.
    """
    if not isinstance(lambda_values, np.ndarray) \
    or not isinstance(lambda_values, list):
        lambda_values = np.array([lambda_values])
    return np.polyval(poly_coeffs[:order+1][::-1], lambda_values)

def energy_change_charge_qc_atom(
    df_qc, target_label, delta_charge, target_initial_charge=0,
    change_signs=False, basis_set='aug-cc-pV5Z',
    ignore_one_row=True):
    """Calculate the energy difference to change the charge of an atom
    using quantum chemistry.

    Quantum chemistry here implies no nuclear charge perturbations (i.e., a 
    lambda of 0). This represents what the direct quantum chemical prediction.

    Parameters
    ----------
    df_qc : :obj:`pandas.DataFrame`
        A pandas dataframe with quantum chemistry data. It should have the
        following columns (from `get_qc_dframe`): system, atomic_numbers,
        charge, multiplicity, n_electrons, qc_method, basis_set, lambda_range,
        finite_diff_delta, finite_diff_acc, poly_coeff.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'c'``, ``'si'``, or ``'f.h'``.
    delta_charge : :obj:`int`
        Overall change in the initial target system.
    target_initial_charge : :obj:`int`
        Specifies the initial charge state of the target system. For example,
        the first ionization energy is the energy difference going from
        charge ``0 -> 1``, so ``target_initial_charge`` must equal ``0``.
    change_signs : :obj:`bool`, optional
        Multiply all energies by -1 (used to predict electron affinities).
        Defaults to ``False``.
    basis_set : :obj:`str`, optional
        Desired basis sets the predictions are from. Defaults to
        ``aug-cc-pV5Z``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.

    Returns
    -------
    :obj:`float`
        Energy required to change the charge of an atom from quantum chemistry
        in Hartrees.
    """
    # Checks.
    assert len(df_qc.iloc[0]['atomic_numbers']) != 2
    assert delta_charge != 0
    if delta_charge < 0: assert change_signs == True
    
    ###   QC DATA FOR INITIAL STATE OF TARGET   ###
    target_initial_qc = df_qc.query(
        'system == @target_label'
        '& charge == @target_initial_charge'
        '& lambda_value == 0'
        '& basis_set == @basis_set'
    )
    
    if len(target_initial_qc) == 0:
        # Often we do not have the data to make the prediction.
        # So we return NaN.
        return np.nan
    else:
        target_initial_qc = select_state(
            target_initial_qc, 0, ignore_one_row=ignore_one_row
        )
        assert len(target_initial_qc) == 1  # Should only have one row.

    ###   QC DATA FOR FINAL STATE OF TARGET   ###
    target_final_n_electrons = target_initial_qc.n_electrons.values[0] - delta_charge
    
    target_final_qc = df_qc.query(
        'system == @target_label'
        '& lambda_value == 0'
        '& n_electrons == @target_final_n_electrons'
        '& basis_set == @basis_set'
    )
    
    if len(target_final_qc) == 0:
        # Often we do not have the data to make the prediction.
        # So we return NaN.
        return np.nan
    else:
        target_final_qc = select_state(
            target_final_qc, 0, ignore_one_row=ignore_one_row
        )
        assert len(target_final_qc) == 1  # Should only have one row.

    ###   COMPUTES ENERGY DIFFERENCE   ###
    e_diff = target_final_qc.iloc[0]['electronic_energy'] - target_initial_qc.iloc[0]['electronic_energy']
    if change_signs:
        e_diff *= -1
    return e_diff

def energy_change_charge_qa_atom(
    df_qc, df_qats, target_label, delta_charge, target_initial_charge=0,
    change_signs=False, basis_set='aug-cc-pV5Z', use_ts=True,
    ignore_one_row=True, considered_lambdas=None, return_qats_vs_qa=False):
    """Calculate the energy difference to change the charge of a target atom
    using quantum alchemy with or without a Taylor series.

    Parameters
    ----------
    df_qc : :obj:`pandas.DataFrame`
        A pandas dataframe with quantum chemistry data. It should have the
        following columns (from `get_qc_dframe`): system, atomic_numbers,
        charge, multiplicity, n_electrons, qc_method, basis_set, lambda_range,
        finite_diff_delta, finite_diff_acc, poly_coeff.
    df_qats : :obj:`pandas.DataFrame`
        A pandas dataframe with QATS data. It should have the
        following columns (from `get_qats_dframe`): system, atomic_numbers,
        charge, multiplicity, n_electrons, qc_method, basis_set, lambda,
        electronic_energy, hf_energy, and correlation_energy.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'c'``, ``'si'``, or ``'f.h'``.
    delta_charge : :obj:`str`
        Overall change in the initial target system.
    target_initial_charge : :obj:`int`
        Specifies the initial charge state of the target system. For example,
        the first ionization energy is the energy difference going from
        charge ``0 -> 1``, so ``target_initial_charge`` must equal ``0``.
    change_signs : :obj:`bool`, optional
        Multiply all predictions by -1. Used to correct the sign for computing
        electron affinities. Defaults to ``False``.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'aug-cc-pV5Z'``.
    use_ts : :obj:`bool`, optional
        Use a Taylor series approximation (with finite differences) to make
        QATS-n predictions (where n is the order). Defaults to ``True``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    considered_lambdas : :obj:`list`, optional
        Allows specification of lambda values that will be considered. ``None``
        will allow all lambdas to be valid, ``[1, -1]`` would only report
        predictions using references using a lambda of ``1`` or ``-1``.
        Defaults to ``None``.
    return_qats_vs_qa : :obj:`bool`, optional
        Return the difference of QATS-n - QA predictions; i.e., the error of
        using a Taylor series with repsect to the alchemical
        PES. Defaults to ``False``.
    
    Returns
    -------
    :obj:`dict`
        Quantum alchemy predictions with or without a Taylor series for the
        energy required to change the charge of an atom. Keys are system labels
        of the references and values are :obj:`numpy.ndarray` of energy
        predictions in Hartrees.
    """
    if return_qats_vs_qa: assert use_ts == True
    assert len(df_qc.iloc[0]['atomic_numbers']) != 2
    assert delta_charge != 0
    if delta_charge < 0: assert change_signs == True

    ###   GETS INFORMATION ON TARGET SYSTEM   ###
    # Selects initial target ground state QC data.
    target_initial_qc = df_qc[
        (df_qc.system == target_label) & (df_qc.charge == target_initial_charge)
        & (df_qc.lambda_value == 0.0) & (df_qc.basis_set == basis_set)
    ]
    
    target_initial_qc = select_state(
        target_initial_qc, 0, ignore_one_row=ignore_one_row
    )
    assert len(target_initial_qc) == 1
    target_initial_n_electrons = target_initial_qc.n_electrons.values[0]
    target_atomic_numbers = target_initial_qc.iloc[0]['atomic_numbers']

    # Selects final target ground state QC data.
    target_final_n_electrons = target_initial_n_electrons - delta_charge

    ###   GETS QUANTUM ALCHEMY REFERENCES   ###
    # Get all available references for the initial target based on ground state
    # energies.
    avail_ref_final_sys = set(
        df_qats[
            (df_qats.system != target_label)
            & (df_qats.n_electrons == target_final_n_electrons)
            & (df_qats.basis_set == basis_set)
        ].system.values
    )
    ref_initial_qats = get_qa_refs(
        df_qc, df_qats, target_label, target_initial_n_electrons,
        basis_set=basis_set
    )
    
    ref_initial_qats = ref_initial_qats[
        ref_initial_qats['system'].isin(avail_ref_final_sys)
    ]
    ref_initial_qats = select_state(
        ref_initial_qats, 0, ignore_one_row=ignore_one_row
    )

    # Get all available references for the final target based on ground state
    # energies.
    ref_final_qats = get_qa_refs(
        df_qc, df_qats, target_label, target_final_n_electrons,
        basis_set=basis_set
    )
    
    ref_final_qats = ref_final_qats[
        ref_final_qats['system'].isin(ref_initial_qats.system)
    ]
    ref_final_qats = select_state(
        ref_final_qats, 0, ignore_one_row=ignore_one_row
    )

    # Checks that the size of initial and final dataframe is the same
    assert len(ref_initial_qats) == len(ref_final_qats)

    ###   MAKE PREDICTIONS   ###
    predictions = {}
    for system in ref_initial_qats.system:
        # Gets lambda value to go from reference to target.
        ref_initial = ref_initial_qats.query('system == @system')
        ref_final = ref_final_qats.query('system == @system')

        lambda_initial = get_lambda_value(
            ref_initial.iloc[0]['atomic_numbers'], target_atomic_numbers,
            specific_atom=None, direction=None
        )
        lambda_final = get_lambda_value(
            ref_final.iloc[0]['atomic_numbers'], target_atomic_numbers,
            specific_atom=None, direction=None
        )

        assert lambda_initial == lambda_final
        if considered_lambdas is not None:
            if lambda_initial not in considered_lambdas:
                continue

        # Predictions with a Taylor series.
        if use_ts or return_qats_vs_qa == True:
            order_preds = []
            for order in range(len(ref_initial.iloc[0]['poly_coeffs'])):
                e_target_initial = qats_prediction(
                    ref_initial.iloc[0]['poly_coeffs'], order, lambda_initial
                )
                e_target_final = qats_prediction(
                    ref_final.iloc[0]['poly_coeffs'], order, lambda_final
                )
                e_diff = (e_target_final - e_target_initial)[0]
                
                if change_signs:
                    e_diff *= -1
                order_preds.append(e_diff)

            predictions[system] = np.array(order_preds)
        # Predictions without a Taylor series or compute the difference.
        if not use_ts or return_qats_vs_qa == True:
            chrg_ref_initial = ref_initial.iloc[0]['charge']
            mult_ref_initial = ref_initial.iloc[0]['multiplicity']
            ref_initial_qc = df_qc.query(
                'system == @system & lambda_value == @lambda_initial'
                '& charge == @chrg_ref_initial'
                '& multiplicity == @mult_ref_initial'
                '& basis_set == @basis_set'
            )
            assert len(ref_initial_qc) == 1
            e_target_initial = ref_initial_qc.iloc[0]['electronic_energy']
            
            chrg_ref_final = ref_final.iloc[0]['charge']
            mult_ref_final = ref_final.iloc[0]['multiplicity']
            ref_final_qc = df_qc.query(
                'system == @system & lambda_value == @lambda_initial'
                '& charge == @chrg_ref_final'
                '& multiplicity == @mult_ref_final'
                '& basis_set == @basis_set'
            )
            
            e_target_final = ref_final_qc.iloc[0]['electronic_energy']
            e_diff = e_target_final - e_target_initial
            if change_signs:
                e_diff *= -1
            
            if return_qats_vs_qa:
                pred_diff = [i - e_diff for i in predictions[system]]
                predictions[system] = np.array(pred_diff)
            else:
                predictions[system] = np.array([e_diff])

    return predictions

def dimer_minimum(bond_lengths, energies, n_points=2, poly_order=4,
    remove_outliers=False, zscore_cutoff=3.0):
    """Interpolate the minimum energy of a dimer with respect to bond length
    using a fitted polynomial to the lowest energies.

    Parameters
    ----------
    bond_lengths : :obj:`numpy.ndarray`
        All bond lengths considered.
    energies : :obj:`numpy.ndarray`
        Corresponding electronic energies.
    n_points : :obj:`int`, optional
        The number of surrounding points on either side of the minimum bond
        length. Defaults to ``2``.
    poly_order : :obj:`int`, optional
        Maximum order of the fitted polynomial. Defaults to ``2``.
    remove_outliers : :obj:`bool`, optional
        Do not include bond lengths that are marked as outliers by their z
        score. Useful if there are cases where one quantum alchemy prediction
        is significantly off (i.e., errors on the order of hundreds of eV).
        Defaults to ``False``.
    zscore_cutoff : :obj:`float`, optional
        Bond length energies that have a z score higher than this are
        considered outliers. Defaults to ``3.0``.
    
    Returns
    -------
    :obj:`float`
        Equilibrium bond length in Angstroms.
    :obj:`float`
        Electronic energy (Hartrees) corresponding to the equilibrium bond
        length.
    """
    bond_lengths_fit, poly_coeffs = fit_dimer_poly(
        bond_lengths, energies, n_points=n_points, poly_order=poly_order,
        remove_outliers=remove_outliers, zscore_cutoff=zscore_cutoff
    )
    eq_bond_length, eq_energy = find_poly_min(
        bond_lengths_fit, poly_coeffs
    )
    return eq_bond_length, eq_energy

def _dimer_curve(df, lambda_value=None, use_ts=False, qats_order=None):
    """Bond lengths and their respective electronic energies using quantum
    chemistry or alchemy.

    Dataframe should only have one system present.

    Parameters
    ----------
    df : :obj:`pandas.dataframe`
        A quantum chemistry or QATS dataframe.
    lambda_value : :obj:`float`, optional
        Nuclear charge perturbation to get from reference to target; required if
        quantum alchemy predictions are desired.
    use_ts : :obj:`bool`, optional
        Make quantum alchemy predictions using a Taylor series with
        energy derivatives from finite differences. Defaults to ``False``.
    qats_order : :obj:`int`, optional
        Taylor series order to be used in QATS predictions.
    
    Returns
    -------
    :obj:`numpy.ndarray`
        All considered bond lengths available for a system in increasing length.
    :obj:`numpy.ndarray`
        Respective energies predicted from either quantum chemistry or alchemy.
    """
    assert len(set(df['system'].values)) == 1 \
           and len(set(df['charge'].values)) == 1 \
           and len(set(df['multiplicity'].values)) == 1
    assert len(df.iloc[0]['atomic_numbers']) == 2

    if use_ts:
        assert 'poly_coeffs' in df.columns
        assert qats_order is not None

        bond_length_order = np.argsort(df['bond_length'].values)
        bond_lengths = []
        energies = []
        for idx in bond_length_order:
            bond_lengths.append(
                df.iloc[idx]['bond_length']
            )
            poly_coeffs = df.iloc[idx]['poly_coeffs']
            energies.append(
                qats_prediction(poly_coeffs, qats_order, lambda_value)[0]
            )
        
        return np.array(bond_lengths), np.array(energies)
    else:
        assert 'electronic_energy' in df.columns
        assert qats_order is None

        if lambda_value is not None:
            df = df.query('lambda_value == @lambda_value')
        
        bond_length_order = np.argsort(df['bond_length'].values)
        bond_lengths = df['bond_length'].values[bond_length_order]
        energies = df['electronic_energy'].values[bond_length_order]
        return np.array(bond_lengths), np.array(energies)

def dimer_bonding_curve(
    df_qc, target_label, target_charge, excitation_level=0, calc_type='qc',
    use_ts=False, df_qats=None, specific_atom=0,
    direction=None, basis_set='cc-pV5Z', n_points=2, poly_order=4,
    remove_outliers=False, zscore_cutoff=3.0, considered_lambdas=None):
    """Compute the equilibrium bond length and energy using a polynomial fit.

    Parameters
    ----------
    df_qc : :obj:`pandas.DataFrame`
        Quantum chemistry dataframe.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'f.h'``.
    target_charge : :obj:`str`
        Overall change in the system.
    excitation_level : :obj:`int`, optional
        Specifies the desired electronic state. ``0`` for ground state and
        ``1`` for first excited state.
    calc_type : :obj:`str`, optional
        Specifies the method of the calculation. Can either be ``'qc'`` or
        ``'alchemy'``. Defaults to ``'qc'``.
    df_qats : :obj:`pandas.DataFrame`, optional
        QATS dataframe. Needs to be specified if ``calc_type == 'alchemy'``.
    qats_order : :obj:`int`, optional
        Taylor series order used for QATS predictions. Defaults to ``2``.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'cc-pV5Z'``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    n_points : :obj:`int`, optional
        The number of surrounding points on either side of the minimum bond
        length. Defaults to ``2``.
    poly_order : :obj:`int`, optional
        Maximum order of the fitted polynomial. Defaults to ``2``.
    remove_outliers : :obj:`bool`, optional
        Do not include bond lengths that are marked as outliers by their z
        score. Defaults to ``False``.
    zscore_cutoff : :obj:`float`, optional
        Bond length energies that have a z score higher than this are
        considered outliers. Defaults to ``3.0``.
    considered_lambdas : :obj:`list`, optional
        Allows specification of lambda values that will be considered. ``None``
        will allow all lambdas to be valid, ``[1, -1]`` would only report
        predictions using references using a lambda of ``1`` or ``-1``.
    
    Returns
    -------
    :obj:`dict`
        The equilibrium bond length from all possible references. For the qc
        method the reference is the same as the system.
    :obj:`dict`
        The equilibrium energy from all possible references.
    """
    assert calc_type in ['qc', 'alchemy']
    df_sys = df_qc.query(
        'system == @target_label'
        '& charge == @target_charge'
    )
    multiplicity_sys = get_multiplicity(
        df_sys.query('lambda_value == 0'), excitation_level
    )
    df_sys = df_sys.query('multiplicity == @multiplicity_sys')

    if calc_type == 'qc':
        df_sys = df_sys.query('lambda_value == 0')
        bl_sys, e_sys = _dimer_curve(df_sys, lambda_value=0)
        bl_sys = np.array(bl_sys)
        e_sys = np.array(e_sys)
        bl_dict = {target_label: bl_sys}
        e_dict = {target_label: e_sys}
        return bl_dict, e_dict
    
    elif calc_type == 'alchemy':
        sys_n_electron = df_sys.iloc[0]['n_electrons']
        sys_atomic_numbers = df_sys.iloc[0]['atomic_numbers']
        if use_ts:
            assert df_qats is not None
            df_selection = 'qats'
        else:
            df_selection = 'qc'
        df_refs = get_qa_refs(
            df_qc, df_qats, target_label, sys_n_electron,
            basis_set=basis_set, df_selection=df_selection,
            excitation_level=excitation_level,
            specific_atom=specific_atom, direction=direction
        )

        ref_system_labels = tuple(set(df_refs['system']))
        bl_dict = {}
        e_dict = {}
        for i in range(len(ref_system_labels)):
            ref_label = ref_system_labels[i]
            df_ref = df_refs.query('system == @ref_label')
            ref_atomic_numbers = df_ref.iloc[0]['atomic_numbers']
            ref_lambda_value = get_lambda_value(
                ref_atomic_numbers, sys_atomic_numbers,
                specific_atom=specific_atom
            )

            if considered_lambdas is not None:
                if ref_lambda_value not in considered_lambdas:
                    continue
            
            if not use_ts:
                bl_ref, e_ref = _dimer_curve(
                    df_ref, lambda_value=ref_lambda_value,
                    use_ts=use_ts, qats_order=None
                )
            else:
                bl_ref = []
                e_ref = []

                max_qats_order = len(df_ref.iloc[0]['poly_coeffs'])
                for qats_order in range(max_qats_order):
                    bl_ref_order, e_ref_order = _dimer_curve(
                        df_ref, lambda_value=ref_lambda_value,
                        use_ts=use_ts, qats_order=qats_order
                    )
                    bl_ref.append(bl_ref_order)
                    e_ref.append(e_ref_order)
                bl_ref = np.array(bl_ref)
                e_ref = np.array(e_ref)
                
            bl_dict[ref_label] = bl_ref
            e_dict[ref_label] = e_ref
        
        return bl_dict, e_dict

def dimer_eq(
    df_qc, target_label, target_charge, excitation_level=0, calc_type='qc',
    use_ts=False, df_qats=None, specific_atom=0,
    direction=None, basis_set='cc-pV5Z', n_points=2, poly_order=4,
    remove_outliers=False, zscore_cutoff=3.0, considered_lambdas=None):
    """Compute the equilibrium bond length from quantum chemistry or alchemy.

    Parameters
    ----------
    df_qc : :obj:`pandas.DataFrame`
        Quantum chemistry dataframe.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'f.h'``.
    target_charge : :obj:`str`
        Overall change in the system.
    excitation_level : :obj:`int`, optional
        Specifies the desired electronic state. ``0`` for ground state and
        ``1`` for first excited state.
    calc_type : :obj:`str`, optional
        Specifies the method of the calculation. Can either be ``'qc'`` or
        ``'alchemy'``. Defaults to ``'qc'``.
    df_qats : :obj:`pandas.DataFrame`, optional
        QATS dataframe. Needs to be specified if ``calc_type == 'alchemy'``.
    qats_order : :obj:`int`, optional
        Taylor series order used for QATS predictions. Defaults to ``2``.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'cc-pV5Z'``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    n_points : :obj:`int`, optional
        The number of surrounding points on either side of the minimum bond
        length. Defaults to ``2``.
    poly_order : :obj:`int`, optional
        Maximum order of the fitted polynomial. Defaults to ``2``.
    remove_outliers : :obj:`bool`, optional
        Do not include bond lengths that are marked as outliers by their z
        score. Defaults to ``False``.
    zscore_cutoff : :obj:`float`, optional
        Bond length energies that have a z score higher than this are
        considered outliers. Defaults to ``3.0``.
    considered_lambdas : :obj:`list`, optional
        Allows specification of lambda values that will be considered. ``None``
        will allow all lambdas to be valid, ``[1, -1]`` would only report
        predictions using references using a lambda of ``1`` or ``-1``.
    
    Returns
    -------
    :obj:`dict`
        The equilibrium bond length from all possible references. For the qc
        method the reference is the same as the system.
    :obj:`dict`
        The equilibrium energy from all possible references.
    """
    assert calc_type in ['qc', 'alchemy']
    
    bl_dict, e_dict = dimer_bonding_curve(
        df_qc, target_label, target_charge, excitation_level=excitation_level,
        calc_type=calc_type, use_ts=use_ts, df_qats=df_qats,
        specific_atom=specific_atom, direction=direction, basis_set=basis_set,
        n_points=n_points, poly_order=poly_order,
        remove_outliers=remove_outliers, zscore_cutoff=zscore_cutoff,
        considered_lambdas=considered_lambdas
    )

    bl_eq_dict = {}
    e_eq_dict ={}
    for sys_label in bl_dict.keys():
        bl_sys = bl_dict[sys_label]
        e_sys = e_dict[sys_label]

        if len(bl_sys.shape) == 1:
            bl_sys = np.array([bl_sys])
            e_sys = np.array([e_sys])

        bl_eq = []
        e_eq = []
        for i in range(len(bl_sys)):
            bl_eq_i, e_eq_i = dimer_minimum(
                bl_sys[i], e_sys[i], n_points=n_points, poly_order=poly_order,
                remove_outliers=remove_outliers, zscore_cutoff=zscore_cutoff
            )
            bl_eq.append(bl_eq_i)
            e_eq.append(e_eq_i)
        bl_eq_dict[sys_label] = np.array(bl_eq)
        e_eq_dict[sys_label] = np.array(e_eq)
    
    return bl_eq_dict, e_eq_dict

def energy_change_charge_qc_dimer(
    df_qc, target_label, delta_charge, target_initial_charge=0,
    change_signs=False, basis_set='cc-pV5Z',
    ignore_one_row=True, n_points=2, poly_order=4, remove_outliers=False,
    zscore_cutoff=3.0):
    """

    Parameters
    ----------
    df_qc : :obj:`pandas.DataFrame`
        A pandas dataframe with quantum chemistry data.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'f.h'``.
    delta_charge : :obj:`str`
        Overall change in the initial target system.
    target_initial_charge : :obj:`int`
        Specifies the initial charge state of the target system. For example,
        the first ionization energy is the energy difference going from
        charge ``0 -> 1``, so ``target_initial_charge`` must equal ``0``.
    change_signs : :obj:`bool`, optional
        Multiply all predictions by -1. Used to correct the sign for computing
        electron affinities. Defaults to ``False``.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'cc-pV5Z'``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    n_points : :obj:`int`, optional
        The number of surrounding points on either side of the minimum bond
        length. Defaults to ``2``.
    poly_order : :obj:`int`, optional
        Maximum order of the fitted polynomial. Defaults to ``2``.
    remove_outliers : :obj:`bool`, optional
        Do not include bond lengths that are marked as outliers by their z
        score. Defaults to ``False``.
    zscore_cutoff : :obj:`float`, optional
        Bond length energies that have a z score higher than this are
        considered outliers. Defaults to ``3.0``.
    
    Returns
    -------
    :obj:`float`
        Quantum chemistry predicted energy change due to changing the charge
        of the system.
    """
    # Checks that a bond_length is provided for dimers.
    assert len(df_qc.iloc[0]['atomic_numbers']) == 2
    
    # Selects initial target ground state QC data.
    target_initial_qc = df_qc[
        (df_qc.system == target_label) & (df_qc.charge == target_initial_charge)
        & (df_qc.lambda_value == 0.0) & (df_qc.basis_set == basis_set)
    ]
    ground_multiplicity_initial = get_multiplicity(target_initial_qc, 0)
    target_initial_qc = target_initial_qc.query(
        'multiplicity == @ground_multiplicity_initial'
    )
    target_initial_n_electrons = target_initial_qc.n_electrons.values[0]
    target_initial_bond_lengths, target_initial_energies = _dimer_curve(
        target_initial_qc, lambda_value=None, use_ts=False,
        qats_order=None
    )
    _, target_initial_energy = dimer_minimum(
        target_initial_bond_lengths, target_initial_energies, n_points=n_points,
        poly_order=poly_order, remove_outliers=remove_outliers,
        zscore_cutoff=zscore_cutoff
    )
    
    # Selects final target ground state QC data.
    target_final_n_electrons = target_initial_n_electrons - delta_charge
    
    target_final_qc = df_qc[
        (df_qc.system == target_label)
        & (df_qc.lambda_value == 0.0)
        & (df_qc.n_electrons == target_final_n_electrons)
        & (df_qc.basis_set == basis_set)
    ]
    ground_multiplicity_final = get_multiplicity(target_final_qc, 0)
    target_final_qc = target_final_qc.query(
        'multiplicity == @ground_multiplicity_final'
    )
    target_final_bond_lengths, target_final_energies = _dimer_curve(
        target_final_qc, lambda_value=None, use_ts=False, qats_order=None
    )
    _, target_final_energy = dimer_minimum(
        target_final_bond_lengths, target_final_energies, n_points=n_points,
        poly_order=poly_order, remove_outliers=remove_outliers,
        zscore_cutoff=zscore_cutoff
    )

    e_diff = target_final_energy - target_initial_energy
    if change_signs:
        e_diff *= -1
    return e_diff

def energy_change_charge_qa_dimer(
    df_qc, df_qats, target_label, delta_charge,
    target_initial_charge=0, change_signs=False, basis_set='cc-pV5Z',
    use_ts=True, lambda_specific_atom=None, lambda_direction=None,
    ignore_one_row=True, poly_order=4, n_points=2, remove_outliers=False,
    considered_lambdas=None, return_qats_vs_qa=False):
    """Use an QATS reference to predict the energy change due to adding or
    removing an electron to dimers.

    The minimum energy from a fitted parabola is used for each state.

    Parameters
    ----------
    df_qc : :obj:`pandas.DataFrame`
        A pandas dataframe with quantum chemistry data. It should have the
        following columns (from `get_qc_dframe`): system, atomic_numbers,
        charge, multiplicity, n_electrons, qc_method, basis_set, lambda_range,
        finite_diff_delta, finite_diff_acc, poly_coeff.
    df_qats : :obj:`pandas.DataFrame`
        A pandas dataframe with QATS data. It should have the
        following columns (from `get_qats_dframe`): system, atomic_numbers,
        charge, multiplicity, n_electrons, qc_method, basis_set, lambda,
        electronic_energy, hf_energy, and correlation_energy.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'c'``, ``'si'``, or ``'f.h'``.
    delta_charge : :obj:`str`
        Overall change in the initial target system.
    target_initial_charge : :obj:`int`, optional
        Specifies the initial charge state of the target system. For example,
        the first ionization energy is the energy difference going from
        charge ``0 -> 1``, so ``target_initial_charge`` must equal ``0``.
        Defaults to ``0``.
    change_signs : :obj:`bool`, optional
        Multiply all predictions by -1. Used to correct the sign for computing
        electron affinities. Defaults to ``False``.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'cc-pV5Z'``.
    use_ts : :obj:`bool`, optional
        Use a Taylor series approximation to make QATS-n predictions
        (where n is the order). Defaults to ``True``.
    lambda_specific_atom : :obj:`int`, optional
        Applies the entire lambda change to a single atom in dimers. For
        example, OH -> FH+ would be a lambda change of +1 only on the first
        atom.
    lambda_direction : :obj:`str`, optional
        Defines the direction of lambda changes for dimers. ``'counter'`` is
        is where one atom increases and the other decreases their nuclear
        charge (e.g., CO -> BF).
        If the atomic numbers of the reference are the same, the first atom's
        nuclear charge is decreased and the second is increased. IF they are
        different, the atom with the largest atomic number increases by lambda.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    poly_order : :obj:`int`, optional
        Maximum order of the fitted polynomial. Defaults to ``2``.
    n_points : :obj:`int`, optional
        The number of surrounding points on either side of the minimum bond
        length. Defaults to ``2``.
    remove_outliers : :obj:`bool`, optional
        Do not include bond lengths that are marked as outliers by their z
        score. Defaults to ``False``.
    considered_lambdas : :obj:`list`, optional
        Allows specification of lambda values that will be considered. ``None``
        will allow all lambdas to be valid, ``[1, -1]`` would only report
        predictions using references using a lambda of ``1`` or ``-1``.
    return_qats_vs_qa : :obj:`bool`, optional
        Return the difference of QATS-n - QATS predictions; i.e., the error of
        using a Taylor series approximation with repsect to the alchemical
        potential energy surface. Defaults to ``False``.
    """    
    assert delta_charge != 0
    assert len(df_qc.iloc[0]['atomic_numbers']) == 2
    if return_qats_vs_qa: assert use_ts == True

    # Selects initial target ground state QC data.
    target_initial_qc = df_qc[
        (df_qc.system == target_label) & (df_qc.charge == target_initial_charge)
        & (df_qc.lambda_value == 0.0) & (df_qc.basis_set == basis_set)
    ]
    
    ground_multiplicity_initial = get_multiplicity(target_initial_qc, 0)
    target_initial_qc = target_initial_qc.query(
        'multiplicity == @ground_multiplicity_initial'
    )
    assert len(target_initial_qc) > 1
    target_initial_n_electrons = target_initial_qc.iloc[0]['n_electrons']
    target_atomic_numbers = target_initial_qc.iloc[0]['atomic_numbers']

    # Performs checks on lambda selections.
    assert lambda_specific_atom is not None or lambda_direction is not None

    # Selects final target ground state QC data.
    target_final_n_electrons = target_initial_n_electrons - delta_charge
    target_final_qc = df_qc[
        (df_qc.system == target_label)
        & (df_qc.charge == target_initial_charge + delta_charge)
        & (df_qc.lambda_value == 0.0) & (df_qc.basis_set == basis_set)
    ]
    ground_multiplicity_final = get_multiplicity(target_final_qc, 0)
    target_final_qc = target_final_qc.query(
        'multiplicity == @ground_multiplicity_final'
    )

    # Get all available references for the initial target based on ground state
    # energies.
    avail_ref_final_sys = set(
        df_qats[
            (df_qats.system != target_label)
            & (df_qats.n_electrons == target_final_n_electrons)
            & (df_qats.basis_set == basis_set)
        ].system.values
    )
    
    ref_initial_qats = df_qats.query(
        'n_electrons == @target_initial_n_electrons'
        '& basis_set == @basis_set'
        '& multiplicity == @ground_multiplicity_initial'
    )
    ref_initial_qats = ref_initial_qats[
        ref_initial_qats['system'].isin(avail_ref_final_sys)
    ]

    # Get all available references for the final target based on ground state
    # energies.
    ref_final_qats = df_qats.query(
        'n_electrons == @target_final_n_electrons'
        '& basis_set == @basis_set'
        '& multiplicity == @ground_multiplicity_final'
    )
    ref_final_qats = ref_final_qats[
        ref_final_qats['system'].isin(ref_initial_qats.system)
    ]

    # Checks that the size of initial and final dataframe is the same
    assert len(ref_initial_qats) == len(ref_final_qats)

    predictions = {}
    for system in set(ref_initial_qats.system):
        ref_initial = ref_initial_qats.query('system == @system')
        ref_final = ref_final_qats.query('system == @system')

        lambda_initial = get_lambda_value(
            ref_initial.iloc[0]['atomic_numbers'], target_atomic_numbers,
            specific_atom=lambda_specific_atom, direction=lambda_direction
        )
        lambda_final = get_lambda_value(
            ref_final.iloc[0]['atomic_numbers'], target_atomic_numbers,
            specific_atom=lambda_specific_atom, direction=lambda_direction
        )
        assert lambda_initial == lambda_final
        if considered_lambdas is not None:
            if lambda_initial not in considered_lambdas:
                continue

        bond_length_order_initial = np.argsort(ref_initial['bond_length'].values)
        bond_length_order_final = np.argsort(ref_final['bond_length'].values)

        if use_ts or return_qats_vs_qa == True:
            order_preds = []
            for order in range(len(ref_initial.iloc[0]['poly_coeffs'])):
                bond_lengths_initial, energies_initial = _dimer_curve(
                    ref_initial, lambda_value=lambda_initial, use_ts=True,
                    qats_order=order
                )
                _, e_target_initial = dimer_minimum(
                    bond_lengths_initial, energies_initial, n_points=n_points,
                    remove_outliers=remove_outliers
                )

                bond_lengths_final, energies_final = _dimer_curve(
                    ref_final, lambda_value=lambda_final, use_ts=True,
                    qats_order=order
                )
                _, e_target_final = dimer_minimum(
                    bond_lengths_final, energies_final, n_points=n_points,
                    remove_outliers=remove_outliers
                )
                
                e_diff = e_target_final - e_target_initial
                if change_signs:
                    e_diff *= -1
                order_preds.append(e_diff)
            predictions[system] = np.array(order_preds)
        if not use_ts or return_qats_vs_qa == True:
            chrg_ref_initial = ref_initial.iloc[0]['charge']
            mult_ref_initial = ref_initial.iloc[0]['multiplicity']
            ref_initial_qc = df_qc.query(
                'system == @system & lambda_value == @lambda_initial'
                '& charge == @chrg_ref_initial'
                '& multiplicity == @mult_ref_initial'
                '& basis_set == @basis_set'
            )
            bond_lengths_initial, energies_initial = _dimer_curve(
                ref_initial_qc, lambda_value=lambda_initial, use_ts=False,
                qats_order=None
            )
            _, e_target_initial = dimer_minimum(
                bond_lengths_initial, energies_initial, n_points=n_points,
                remove_outliers=remove_outliers
            )
            
            chrg_ref_final = ref_final.iloc[0]['charge']
            mult_ref_final = ref_final.iloc[0]['multiplicity']
            ref_final_qc = df_qc.query(
                'system == @system & lambda_value == @lambda_initial'
                '& charge == @chrg_ref_final'
                '& multiplicity == @mult_ref_final'
                '& basis_set == @basis_set'
            )
            bond_lengths_final, energies_final = _dimer_curve(
                ref_final_qc, lambda_value=lambda_final, use_ts=False, qats_order=None
            )
            _, e_target_final = dimer_minimum(
                bond_lengths_final, energies_final, n_points=n_points,
                remove_outliers=remove_outliers
            )
            
            e_diff = e_target_final - e_target_initial
            if change_signs:
                e_diff *= -1
            
            if return_qats_vs_qa:
                pred_diff = [i - e_diff for i in predictions[system]]
                predictions[system] = np.array(pred_diff)
            else:
                predictions[system] = np.array([e_diff])

    return predictions

def mult_gap_qc_atom(
    df_qc, target_label, target_charge=0,
    basis_set='aug-cc-pV5Z', ignore_one_row=True):
    """Multiplicity gap predictions of atoms using quantum chemistry.

    Parameters
    ----------
    df_qc : :obj:`pandas.dataframe`
        Quantum chemistry dataframe.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'c'``, ``'si'``, or ``'f.h'``.
    target_charge : :obj:`int`
        The system charge.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'aug-cc-pV5Z'``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.

    Returns
    -------
    :obj:`numpy.float64`
        Difference in energy between ground and excited state in Hartrees.
    """
    # Selects initial target ground state QC data.
    target_qc = df_qc[
        (df_qc.system == target_label)
        & (df_qc.charge == target_charge)
        & (df_qc.lambda_value == 0.0)
        & (df_qc.basis_set == basis_set)
    ]
    if len(target_qc) == 0 or len(target_qc) == 1:
        # Often we do not have the data to make the prediction.
        # So we return NaN.
        return np.nan
    elif len(target_qc) > 1:
        target_initial_qc = select_state(
            target_qc, 0, ignore_one_row=ignore_one_row
        )
        assert len(target_initial_qc) == 1  # Should only have one row.
        target_final_qc = select_state(
            target_qc, 1, ignore_one_row=ignore_one_row
        )
        assert len(target_final_qc) == 1  # Should only have one row.

    e_diff = target_final_qc.iloc[0]['electronic_energy'] \
             - target_initial_qc.iloc[0]['electronic_energy']
    return e_diff

def mult_gap_qa_atom(
    df_qc, df_qats, target_label, target_charge=0,
    basis_set='aug-cc-pV5Z', use_ts=True, ignore_one_row=True,
    considered_lambdas=None, return_qats_vs_qa=False
):
    """Multiplicity gap predictions of atoms using quantum alchemy.

    Parameters
    ----------
    df_qc : :obj:`pandas.dataframe`
        Quantum chemistry dataframe.
    df_qats : :obj:`pandas.DataFrame`
        A pandas dataframe with QATS data.
    target_label : :obj:`str`
        Atoms in the system. For example, ``'c'``, ``'si'``, or ``'f.h'``.
    target_charge : :obj:`int`, optional
        The system charge. Defaults to ``0``.
    basis_set : :obj:`str`, optional
        Specifies the basis set to use for predictions. Defaults to
        ``'aug-cc-pV5Z'``.
    ignore_one_row : :obj:`bool`, optional
        Used to control errors in ``state_selection`` when there is missing
        data (i.e., just one state). If ``True``, no errors are raised. Defaults
        to ``True``.
    considered_lambdas : :obj:`list`, optional
        Allows specification of lambda values that will be considered. ``None``
        will allow all lambdas to be valid, ``[1, -1]`` would only report
        predictions using references using a lambda of ``1`` or ``-1``.
    return_qats_vs_qa : :obj:`bool`, optional
        Return the difference of QATS-n - QATS predictions; i.e., the error of
        using a Taylor series approximation with repsect to the alchemical
        potential energy surface. Defaults to ``False``.

    Returns
    -------
    :obj:`dict`
        Difference in energy between ground and excited state in Hartrees
        (values) for each quantum alchemy reference (keys).
    """
    if return_qats_vs_qa:
        assert use_ts == True

    # Selects initial target ground state QC data.
    target_qc = df_qc[
        (df_qc.system == target_label)
        & (df_qc.charge == target_charge)
        & (df_qc.lambda_value == 0.0)
        & (df_qc.basis_set == basis_set)
    ]
    if len(target_qc) == 0 or len(target_qc) == 1:
        # Often we do not have the data to make the prediction.
        # So we return nothing.
        return {}
    elif len(target_qc) > 1:
        n_electrons = list(set(target_qc.n_electrons.values))
        assert len(n_electrons) == 1
        n_electrons = n_electrons[0]
        target_initial_qc = select_state(
            target_qc, 0, ignore_one_row=ignore_one_row
        )
        assert len(target_initial_qc) == 1  # Should only have one row.
        target_final_qc = select_state(
            target_qc, 1, ignore_one_row=ignore_one_row
        )
        assert len(target_final_qc) == 1  # Should only have one row.
    target_atomic_numbers = target_initial_qc.iloc[0]['atomic_numbers']
    

    ref_qats = get_qa_refs(
        df_qc, df_qats, target_label, n_electrons,
        basis_set=basis_set
    )
    if len(ref_qats) == 0 or len(ref_qats) == 1:
        # Often we do not have the data to make the prediction.
        # So we return nothing.
        return {}
    elif len(ref_qats) > 1:
        ref_initial_qats = select_state(
            ref_qats, 0, ignore_one_row=ignore_one_row
        )
        ref_final_qats = select_state(
            ref_qats, 1, ignore_one_row=ignore_one_row
        )

    # Checks that the size of initial and final dataframe is the same
    assert len(ref_initial_qats) == len(ref_final_qats)

    predictions = {}
    for system in ref_initial_qats.system:
        ref_initial = ref_initial_qats.query('system == @system')
        lambda_initial = get_lambda_value(
            ref_initial.iloc[0]['atomic_numbers'], target_atomic_numbers
        )
        
        ref_final = ref_final_qats.query('system == @system')
        lambda_final = get_lambda_value(
            ref_final.iloc[0]['atomic_numbers'], target_atomic_numbers
        )

        assert lambda_initial == lambda_final
        if considered_lambdas is not None:
            if lambda_initial not in considered_lambdas:
                continue

        if use_ts or return_qats_vs_qa == True:
            order_preds = []
            for order in range(len(ref_initial.iloc[0]['poly_coeffs'])):
                e_target_initial = qats_prediction(
                    ref_initial.iloc[0]['poly_coeffs'], order, lambda_initial
                )
                e_target_final = qats_prediction(
                    ref_final.iloc[0]['poly_coeffs'], order, lambda_final
                )
                e_diff = (e_target_final - e_target_initial)[0]
                order_preds.append(e_diff)
            predictions[system] = np.array(order_preds)
        if not use_ts or return_qats_vs_qa == True:
            chrg_ref_initial = ref_initial.iloc[0]['charge']
            mult_ref_initial = ref_initial.iloc[0]['multiplicity']
            
            ref_initial_qc = df_qc.query(
                'system == @system & lambda_value == @lambda_initial'
                '& charge == @chrg_ref_initial'
                '& multiplicity == @mult_ref_initial'
                '& basis_set == @basis_set'
            )
            assert len(ref_initial_qc) == 1
            e_target_initial = ref_initial_qc.iloc[0]['electronic_energy']
            
            chrg_ref_final = ref_final.iloc[0]['charge']
            mult_ref_final = ref_final.iloc[0]['multiplicity']
            ref_final_qc = df_qc.query(
                'system == @system & lambda_value == @lambda_initial'
                '& charge == @chrg_ref_final'
                '& multiplicity == @mult_ref_final'
                '& basis_set == @basis_set'
            )
            e_target_final = ref_final_qc.iloc[0]['electronic_energy']
            e_diff = e_target_final - e_target_initial
            
            if return_qats_vs_qa:
                pred_diff = [i - e_diff for i in predictions[system]]
                predictions[system] = np.array(pred_diff)
            else:
                predictions[system] = np.array([e_diff])

    return predictions

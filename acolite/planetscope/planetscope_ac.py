## def planetscope_ac
## ACOLITE for PlanetScope
## written by Quinten Vanhellemont, RBINS for the PONDER project
## 2018-03-14
## modifications: 2018-03-15 (QV) added zip option, image_file in metadata, added netcdf support
##                2018-03-19 (QV) added removal of extracted bundle
##                2018-03-20 (QV) added check for PlanetScope_0d
##                2018-03-21 (QV) added removal of intermediate L1R NetCDF
##                2018-04-23 (QV) added nc_compression
##                2018-05-08 (QV) changed Rapideye output name
##                2019-03-25 (QV) added wvlut max ths
##                2019-06-12 (QV) added new model selection

def planetscope_ac(bundle, output, limit=None,
                   gas_transmittance = True,
                   uoz_default = 0.3,
                   uwv_default = 1.5,
                   wvlut = '201710C',
                   ## use ancillary data for gas transmittances rather than defaults
                   ancillary_data = True,
                   ## do sky glint correction
                   sky_correction = True,
                   sky_correction_option = 'all',
                   lut_pressure = True,
                   pressure = None,
                   model_selection='min_tau',
                   rdark_list_selection='intercept',
                   luts=['PONDER-LUT-201704-MOD1-1013mb', 'PONDER-LUT-201704-MOD2-1013mb'],
                   extend_limit=False,
                   keep_l1r_ncdf=False,
                   map_rgb = True,
                   map_rgb_rhos = True,
                   rgb_autorange = False,
                   rgb_percentiles = [10,90],
                   rgb_range_min = [0.0,0.0,0.0],
                   rgb_range_max = [0.15,0.15,0.15], nc_compression=True):
    
    import os
    from numpy import nanmax,nanmin,nanpercentile

    from acolite.shared import nc_gatts, nc_datasets, nc_data, rtoa_to_rhos
    from acolite.output import nc_write, write_rgb
    from acolite.plotting import plot_dark_spectrum
    from acolite import planetscope, ac

    import acolite as aco

    data_type=None
    sub = None
    sr_image_file = None

    if bundle[-3:] == '.nc': 
        try:
            import dateutil.parser
            metadata = nc_gatts(bundle)
            ## fix some metadata not supported in NetCDF
            metadata['TIME'] = dateutil.parser.parse(metadata["isotime"])
            for mk in metadata:
                if ('BAND' in mk):
                    metadata[mk]=metadata[mk].split(',')
            data_type = "NetCDF"
        except:
            data_type = None
    
    zipped=False
    if data_type == None:
        data_type = 'PlanetScope'
        if bundle[-4:] == '.zip':
             zipped=True
             import zipfile, shutil
             bundle_orig = '{}'.format(bundle)
             bundle,ext = os.path.splitext(bundle_orig)
             zip_ref = zipfile.ZipFile(bundle_orig, 'r')
             zip_ref.extractall(bundle)
             zip_ref.close()

        files = planetscope.bundle_test(bundle)

        metafile = None
        image_file = None

        if 'metadata' in files: metafile = files['metadata']['path']     
        if 'analytic' in files: image_file = files['analytic']['path']
        if 'sr' in files: sr_image_file = files['sr']['path']     
    
        metadata = planetscope.parse_metadata(metafile)
        metadata['image_file'] = image_file
        
        if limit is not None:
            ret = planetscope.geo.get_sub(metadata, limit)
            if type(ret) == int:
                print('Error computing subset.')
                return(1)
            sub, p, (xrange,yrange,grid_region) = ret

    sensor = metadata['LUT_SENSOR']

    if sensor == 'PlanetScope_0d':
        print('Sensor {} not yet implemented'.format(sensor))
        return()

    if ('lat' not in locals()) or ('lat' not in locals()):
        #print('Computing lat lon')
        if (data_type == "NetCDF") & ('limit' in metadata) & (limit is None):
            datasets = nc_datasets(bundle)
            print(datasets)
            if ('lon' in datasets) & ('lat' in datasets):
                lon = nc_data(bundle, 'lon')
                lat = nc_data(bundle, 'lat')
            else:
                lon, lat = planetscope.get_ll(metadata,limit=metadata['limit'],extend_limit=True)
        else:
            lon, lat = planetscope.get_ll(metadata,limit=limit,extend_limit=extend_limit)

    ## get NCEP & TOAST ancillary data
    if ancillary_data:
        #if ('lat' not in locals()) or ('lat' not in locals()):
            #if data_type == "NetCDF":
            #    lon = nc_data(bundle, 'lon')
            #    lat = nc_data(bundle, 'lat')
            #else:
            #    lon, lat = planetscope.get_ll(metadata,limit=limit,extend_limit=extend_limit)

        ## use image/region mid-point
        pc_lon=lon[int(lon.shape[0]/2), int(lon.shape[1]/2)]
        pc_lat=lat[int(lat.shape[0]/2), int(lat.shape[1]/2)]
        pc_date = metadata['TIME'].strftime('%Y-%m-%d')
        pc_time=metadata['TIME'].hour + metadata['TIME'].minute/60. + metadata['TIME'].second/3600.
        pc_anc = ac.ancillary.ancillary_get(pc_date, pc_lon, pc_lat, ftime=pc_time, kind='nearest')
            
        ## get pressure from ancillary data if not determined by user or by DEM
        if (pressure == None) & (lut_pressure):
            if 'press' not in pc_anc: 
                print('No ancillary pressure found: using default.')
                pressure=None
            else: pressure = pc_anc['press']['interp']

    ## get gas transmittances
    if gas_transmittance:
        uoz=uoz_default
        uwv=uwv_default
        
        ## use ancillary data if provided
        if ancillary_data:
            if 'ozone' in pc_anc: uoz=pc_anc['ozone']['interp']
            else: print('No ancillary ozone found: using default {}.'.format(uoz))
            if 'p_water' in pc_anc: uwv=pc_anc['p_water']['interp']/10.
            else:print('No ancillary ozone found: using default {}.'.format(uwv))
        ## compute transmittances
        tt_oz = ac.o3_transmittance(sensor, metadata, uoz=uoz)
        tt_wv = ac.wvlut_interp(min(79.999, metadata['THS']), metadata['THV'], uwv=uwv, sensor=sensor, config=wvlut)
        tt_gas = {btag: tt_oz[btag] * tt_wv[btag] for btag in tt_oz.keys()}

    ## Sky reflectance correction
    if sky_correction:
        rsky = ac.toa_rsky(metadata, pressure=pressure)
            
    if not os.path.exists(output): os.makedirs(output)
        
    if data_type == "NetCDF":
        obase = metadata['obase']
        nc_l1r_new = False
        nc_file_l1r = '{}'.format(bundle)
        #if ('lat' not in locals()) or ('lat' not in locals()):
        #    lon = nc_data(bundle, 'lon')
        #    lat = nc_data(bundle, 'lat')
    else:
        ## add PS satellite id
        if metadata['SENSOR']=='PlanetScope':
            obase = '{}_{}_{}'.format(metadata['SENSOR'], metadata['TIME'].strftime('%Y_%m_%d_%H_%M_%S'), 'PS{}'.format(metadata['SATELLITE_SENSOR'].split('_')[1]))
        else:
            #obase = '{}_{}'.format(metadata['SATELLITE_SENSOR'], metadata['TIME'].strftime('%Y_%m_%d_%H_%M_%S'))
            obase = '{}_{}_{}'.format(metadata['SENSOR'], metadata['TIME'].strftime('%Y_%m_%d_%H_%M_%S'), 'RE{}'.format(metadata['SATELLITE_SENSOR'].split('-')[1]))
        nc_l1r_new = True
        nc_file_l1r = '{}/{}_L1R.nc'.format(output, obase)
    
    nc_file_l2r = '{}/{}_L2R.nc'.format(output, obase)
    bands = metadata['BANDS_ALL']

    if extend_limit:
        offset = grid_region['off']
        global_dims = (grid_region['dims'][1],grid_region['dims'][0])
    else:
        offset = None
        global_dims = None
            
    ## read RTOA and get rdark
    rdark = {}
    rhod = {}

    for bi, band in enumerate(bands):
        #ds_att = {}
        #for mk in metadata:
        #    if '{}-'.format(band) not in mk: continue
        #    bk, bp = mk.split('-')
        #    ds_att[bp] = metadata[mk]
        #ds_att['wavelength']=float(metadata['{}-{}'.format(band, 'wave_name')])

        #parname_t = 'rhot_{}'.format(ds_att['wave_name'])
        ds_att = planetscope.get_band_att(metadata, band)
        parname_t = 'rhot_{}'.format(ds_att['wave_name'])
        parname_s = 'rhos_{}'.format(ds_att['wave_name'])

        print(parname_t)
        
        if data_type == "NetCDF":
            band_data = nc_data(bundle, parname_t)
        else:
            band_data = planetscope.get_rtoa(image_file, bi+1, band, metadata, sub=sub)
            ## write to L1R NetCDF
            nc_write(nc_file_l1r, parname_t, band_data, 
                         dataset_attributes=ds_att, 
                          new=nc_l1r_new, attributes=metadata, global_dims=global_dims, offset=offset, nc_compression=nc_compression)
            nc_l1r_new=False
        
        ## apply gas correction
        if gas_transmittance: 
            band_data/=tt_gas[band]
            ds_att['tt_gas'] = tt_gas[band]
        
        ## apply sky correction
        if sky_correction:
            if sky_correction_option == 'all':
                band_data -= rsky[band]
                ds_att['rsky'] = rsky[band]

        ## get rdark
        rdark[band] = nanpercentile(band_data, (0.1))
            
        rhod[band] = {'rhod':rdark[band], 'wave':ds_att['wave']*1000., 'tt_gas':tt_gas[band],
                           'raa': metadata['AZI'],'vza': metadata['THV'], 'sza': metadata['THS']}
        band_data = None

    ## select model
    #(ratm_s,rorayl_s,dtotr_s,utotr_s,dtott_s,utott_s,astot_s, tau550),\
    #(bands_sorted, tau550_all_bands, dark_idx, sel_rmsd, rdark_sel, pixel_idx), \
    #(sel_model_lut, sel_model_lut_meta) = ac.select_model(metadata, rdark, luts=luts,
    #                                                           model_selection=model_selection, 
    #                                                           rdark_list_selection=rdark_list_selection,
    #                                                           pressure=pressure)
    #print(tau550, dark_idx, sel_model_lut_meta['aermod'])

    #print(rhod)
    res = aco.ac.select_model2(rhod, sensor, pressure = pressure, 
                               rhod_tgas_cutoff = 0.90, rhod_model_selection = 'min_tau')
    #print(res)
    #print(res.keys())
    attributes = metadata
                
    ## a/c parameters
    pars = ['romix','dtott','utott','astot', 'rorayl']

    ## get sensor RSR
    rsr_file = '{}/RSR/{}.txt'.format(aco.config['pp_data_dir'], sensor)
    rsr, rsr_bands = aco.shared.rsr_read(file=rsr_file)

    raa = metadata['AZI']
    vza = metadata['THV']
    sza = metadata['THS']
    waves_mu = res['lut_meta']['wave']

    band_pars = {b:{} for b in rhod}
    for ip, par in enumerate(pars):
        ip = [i for i,value in enumerate(res['lut_meta']['par']) if value == par]
        if len(ip) == 1: ip = ip[0] 
        else: continue
        ret = res['rgi']((ip, waves_mu, raa, vza, sza, res['taua']))
         
        for b in rhod:
            band_pars[b][par] = aco.shared.rsr_convolute(ret, waves_mu, rsr[b]['response'], rsr[b]['wave'])

    #print(band_pars)
    #for b in rdark_sel: attributes['{}-rdark'.format(b)] = rdark_sel[b]
    #for b in ratm_s: attributes['{}-rpath'.format(b)] = ratm_s[b]
    
    for b in res['rhod_sel']: attributes['{}-rdark'.format(b)] = res['rhod_sel'][b]
    for b in band_pars: attributes['{}-rpath'.format(b)] = band_pars[b]['romix']
    
    sel_model_lut_meta = res['lut_meta']
    dark_idx = str(bands[res['sel_idx']])
    tau550 = res['taua']
    sel_rmsd = res['rmsd']

    #print(attributes['rdark'])
    if 'aermod' in sel_model_lut_meta.keys():
        if sel_model_lut_meta['aermod'][0] == "1": model_char = 'C'
        if sel_model_lut_meta['aermod'][0] == "2": model_char = 'M'
        if sel_model_lut_meta['aermod'][0] == "3": model_char = 'U'
    else:
        model_char = '4C'
        model_char = '4C: {}/{}/{}/{}'.format(sel_model_lut_meta['mod1'],sel_model_lut_meta['mod2'],sel_model_lut_meta['mod3'],sel_model_lut_meta['mod4'])

    pixel_idx = -1
    attributes['dsf_pixel_idx']=pixel_idx
    attributes['dsf_percentile']=0.1
    #attributes['dsf_bestfit']=bestfit
    attributes['dsf_model_selection']=model_selection

    attributes['ac_model']=sel_model_lut_meta['base']#[0]
    attributes['ac_model_char']=model_char
    if type(dark_idx) == str:
        attributes['ac_band']=dark_idx
    else:
        attributes['ac_band']=','.join(dark_idx)

    attributes['ac_aot550']=tau550
    attributes['ac_rmsd']=sel_rmsd
    print('model:{} band:{} aot={:.3f}'.format(attributes['ac_model_char'],attributes['ac_band'],attributes['ac_aot550']))
    
    ## plot dark spectrum
    ds_plot = '{}/{}_{}.{}'.format(output,obase, 'dark_spectrum','png')
    band_names = bands
    data_type = 'NetCDF'
    #waves = [metadata['bands'][b]['wave_name'] for b in bands]
    waves = [metadata['{}-{}'.format(b,'wave_name')] for b in bands]
    dsf_spectrum_option = 'fixed'

    #metadata['SENSOR']='PlanetScope'
    ratm_s = {b:band_pars[b]['romix'] for b in band_pars}
    rorayl_s = {b:band_pars[b]['rorayl'] for b in band_pars}
    plot_dark_spectrum(metadata, ds_plot, waves, ratm_s, rorayl_s, rdark, dark_idx, tau550, sel_model_lut_meta, xlim=(450,900))

    ## compute RHOS
    nc_l2r_new = True

    for bi, band in enumerate(bands):
        #ds_att = {}
        #for mk in metadata:
        #    if '{}-'.format(band) not in mk: continue
        #    bk, bp = mk.split('-')
        #    ds_att[bp] = metadata[mk]
        #ds_att['wavelength']=float(metadata['{}-{}'.format(band, 'wave_name')])

        ds_att = planetscope.get_band_att(metadata, band)
        parname_t = 'rhot_{}'.format(ds_att['wave_name'])
        parname_s = 'rhos_{}'.format(ds_att['wave_name'])

#        parname_t = 'rhot_{}'.format(metadata['bands'][band]['wave_name'])
#        parname_s = 'rhos_{}'.format(metadata['bands'][band]['wave_name'])
        
        ## read from L1R NetCDF
        band_data = nc_data(nc_file_l1r,parname_t)
        #ds_att = metadata['bands'][band]
        #ds_att['wavelength']=float(metadata['bands'][band]['wave_name'])

        #if ('lat' not in locals()) or ('lat' not in locals()):
        #    
        #    lon, lat = planetscope.geo.get_ll(metadata,limit=limit,extend_limit=extend_limit)

        nc_write(nc_file_l2r, 'lon', lon,
                 new=nc_l2r_new, attributes=attributes, nc_compression=nc_compression)
        nc_l2r_new=False

        nc_write(nc_file_l2r, 'lat', lat,
                 new=nc_l2r_new, attributes=attributes, nc_compression=nc_compression)
        nc_l2r_new=False

        ## write rhot
        nc_write(nc_file_l2r, parname_t, band_data, 
                 dataset_attributes=ds_att, 
                 new=nc_l2r_new, attributes=attributes, nc_compression=nc_compression)
        nc_l2r_new=False

        ## apply gas correction
        if gas_transmittance: 
            band_data/=tt_gas[band]
            ds_att['tt_gas'] = tt_gas[band]

        ## apply sky correction
        if sky_correction:
            if sky_correction_option == 'all':
                band_data -= rsky[band]
                ds_att['rsky'] = rsky[band]

        for k in band_pars[band]: ds_att[k] = band_pars[band][k]

        ## compute rhos
        #band_data = rtoa_to_rhos(band_data, ratm_s[band], utott_s[band], dtott_s[band], astot_s[band], tt_gas = 1.)
        band_data = rtoa_to_rhos(band_data, ds_att['romix'], ds_att['utott'], ds_att['dtott'], ds_att['astot'], tt_gas = 1.)
        nc_write(nc_file_l2r, parname_s, band_data, 
                            dataset_attributes=ds_att, 
                            new=nc_l2r_new, attributes=attributes, nc_compression=nc_compression)
        nc_l2r_new=False
                 
    ## make RGB
    #wave_red = metadata['bands']['Red']['wave_name']
    #wave_green = metadata['bands']['Green']['wave_name']
    #wave_blue = metadata['bands']['Blue']['wave_name']
    wave_red = metadata['Red-wave_name']
    wave_green = metadata['Green-wave_name']
    wave_blue = metadata['Blue-wave_name']

    ## map rgb images
    ## keep image 3d matrix for further plotting (if needed)
    rgb_image = None
    if map_rgb:
        for par in ['rhot','rhos']:
            rgb_dir = '{}'.format(output)
            if not os.path.exists(rgb_dir): os.makedirs(rgb_dir)
            if (par == 'rhos') & (map_rgb_rhos == False): continue

            ## read data from NCDF file
            data_r = nc_data(nc_file_l2r, '{}_{}'.format(par,wave_red))
            data_g = nc_data(nc_file_l2r, '{}_{}'.format(par,wave_green))
            data_b = nc_data(nc_file_l2r, '{}_{}'.format(par,wave_blue))

            rgb_file = '{}/{}_{}.{}'.format(rgb_dir,obase,'RGB_{}'.format(par.upper()),'png')
            rgb_image = write_rgb(rgb_file, data_r, data_g, data_b, 
                                    rgb_autorange=rgb_autorange, rgb_percentiles=rgb_percentiles,
                                    rgb_range_min=rgb_range_min,rgb_range_max=rgb_range_max, return_image=True)
            rgb_image = None
            data_r = None
            data_g = None
            data_b = None
                        
                        
    ## get PlanetScope surface reflectance
    if sr_image_file is not None:
        nc_file_sr = '{}/{}_SR.nc'.format(output, obase)

        nc_sr_new = True
        attributes['auto_grouping'] = 'rhot:rhorc:rhos:rhow:sr'

        for bi, band in enumerate(bands):
            parname_sr = 'sr_{}'.format(metadata['bands'][band]['wave_name'])
            parname_s = 'rhos_{}'.format(metadata['bands'][band]['wave_name'])

            band_data = planetscope.get_rsur(sr_image_file, bi+1, sub=sub)

            ds_att = metadata['bands'][band]
            ds_att['wavelength']=float(metadata['bands'][band]['wave_name'])

            nc_write(nc_file_sr, parname_sr, band_data, 
                                  dataset_attributes=ds_att, 
                                  new=nc_sr_new, attributes=metadata, global_dims=global_dims, offset=offset, nc_compression=nc_compression)
            nc_sr_new=False

            ## find out overlap with L1 product to save in the same file
            if True:
                data_rhos = nc_data(nc_file_l2r, parname_s)
                nc_write(nc_file_sr, parname_s, data_rhos, 
                                       dataset_attributes=ds_att, 
                                       new=nc_sr_new, attributes=metadata, nc_compression=nc_compression)
                nc_sr_new=False
                
    if False:
        ## read data from NCDF file
        data_r = nc_data(nc_file_l2r, '{}_{}'.format('rhos',wave_red))

    ## remove the extracted bundle
    if zipped:
         shutil.rmtree(bundle)
         bundle = '{}'.format(bundle_orig)

    if (not keep_l1r_ncdf) & (not data_type == "NetCDF"):
         shutil.rmtree(nc_file_l1r)

    return(nc_file_l2r)
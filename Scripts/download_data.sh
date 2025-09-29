wget https://data.geo.admin.ch/ch.swisstopo.swissboundaries3d/swissboundaries3d_2025-04/swissboundaries3d_2025-04_2056_5728.shp.zip -O ../Data/boundaries.shp.zip
wget https://dam-api.bfs.admin.ch/hub/api/dam/assets/34787122/master -O ../Data/volksabstimmungen.px

unzip ../Data/boundaries.shp.zip -d swissBOUNDARIES3D/
rm ../Data/boundaries.shp.zip

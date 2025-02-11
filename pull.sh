curl --header "Private-Token: wFtojSgu_r8s8WERMxFh" -O -J "https://gitlab.mobiera.com/api/v4/projects/351/jobs/artifacts/main/download?job=build"

if [ $? -eq 0 ]; then
  echo "Successful download. Extracting..."
  unzip -o -d public/reactbuild/ artifacts.zip
  if [ $? -eq 0 ]; then
    echo "Extraction successful."
    mv public/reactbuild/build/* public/reactbuild/.
    rm -r public/reactbuild/build
    rm artifacts.zip
  else
    echo "Error in extraction."
  fi
else
  echo "Error in downloading artifacts."
fi
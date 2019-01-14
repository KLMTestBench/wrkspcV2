FIND_PACKAGE( ROOT REQUIRED)
file(GLOB_RECURSE src_files  "src/*.cpp" "src/*.cc" "src/*.cxx"  )
file(GLOB_RECURSE INCS "*.h" "*.hh" "*.hpp")



add_library (KLM_lib SHARED  ${src_files} ${INCS})
source_group(TREE ${CMAKE_CURRENT_SOURCE_DIR} FILES ${src_files}  )
source_group(TREE ${CMAKE_CURRENT_SOURCE_DIR} FILES ${INCS}  )
ADD_GEN_ROOT_DICT_AUTO_LINK(KLM_lib   -I${CMAKE_CURRENT_SOURCE_DIR}/include)

TARGET_LINK_LIBRARIES(KLM_lib PUBLIC CERN_ROOT)
target_compile_features(KLM_lib PUBLIC cxx_generic_lambdas cxx_auto_type cxx_variadic_templates cxx_inheriting_constructors )
target_include_directories(KLM_lib PUBLIC ./include)



INSTALL(TARGETS KLM_lib  
  RUNTIME DESTINATION bin
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib)
